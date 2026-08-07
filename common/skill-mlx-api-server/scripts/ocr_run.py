#!/usr/bin/env python3
"""
Unlimited-OCR Runner — runs Baidu's Unlimited-OCR on CPU or Apple Silicon (MPS).
Outputs the resulting Markdown text to stdout.
"""

import argparse
import logging
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Configure logging to stderr so it doesn't clutter stdout (which contains our markdown result)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("ocr_runner")

def pdf_to_images(pdf_path, dpi=200):
    """Convert PDF pages to image files using PyMuPDF (fitz)."""
    import fitz  # PyMuPDF
    logger.info("Converting PDF to images (DPI=%d)...", dpi)
    doc = fitz.open(pdf_path)
    tmp_dir = tempfile.mkdtemp(prefix='ocr_pdf_')
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    paths = []
    for i, page in enumerate(doc):
        out = os.path.join(tmp_dir, f'page_{i+1:04d}.png')
        page.get_pixmap(matrix=mat).save(out)
        paths.append(out)
    doc.close()
    logger.info("Converted %d pages to images.", len(paths))
    return tmp_dir, paths

def main():
    parser = argparse.ArgumentParser(description="Run Baidu Unlimited-OCR inference.")
    parser.add_argument('--input', required=True, help='Path to PDF or image')
    parser.add_argument('--dpi', type=int, default=200, help='DPI for PDF rendering')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input path %s does not exist", input_path)
        sys.exit(1)

    # Late imports to avoid slow startup when parsing args
    import torch
    from transformers import AutoModel, AutoTokenizer

    # Determine hardware acceleration
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    logger.info("Using device: %s", device)

    # Monkey patch to handle hardcoded .cuda() calls in Baidu's remote modeling code
    if device != "cuda":
        logger.info("Monkey patching torch.Tensor.cuda() and torch.nn.Module.cuda() to redirect to %s...", device)
        def _cuda_tensor_patch(self, *args, **kwargs):
            return self.to(device)
        def _cuda_module_patch(self, *args, **kwargs):
            return self.to(device)
        torch.Tensor.cuda = _cuda_tensor_patch
        torch.nn.Module.cuda = _cuda_module_patch

    model_name = "baidu/Unlimited-OCR"
    logger.info("Loading model and tokenizer '%s'...", model_name)
    
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    
    # Load model weights in torch.bfloat16 to match input data type and prevent type mismatch errors
    model = AutoModel.from_pretrained(
        model_name,
        trust_remote_code=True,
        use_safetensors=True,
        torch_dtype=torch.bfloat16
    ).to(device).eval()
    logger.info("Model loaded successfully.")

    # Determine input type
    is_pdf = input_path.suffix.lower() == '.pdf'
    tmp_dir = None
    
    if is_pdf:
        tmp_dir, image_files = pdf_to_images(str(input_path), dpi=args.dpi)
    else:
        # Single image
        image_files = [str(input_path)]

    output_dir = tempfile.mkdtemp(prefix='ocr_out_')
    logger.info("Starting inference on %d images...", len(image_files))
    
    try:
        model.infer_multi(
            tokenizer,
            prompt="<image>Multi page parsing.",
            image_files=image_files,
            output_path=output_dir,
            image_size=1024,
            max_length=32768,
            save_results=True
        )
        
        # Read the generated markdown result
        md_files = [f for f in os.listdir(output_dir) if f.endswith('.md')]
        if md_files:
            md_path = os.path.join(output_dir, md_files[0])
            with open(md_path, 'r', encoding='utf-8') as f:
                # Print result to stdout
                print(f.read())
            logger.info("OCR completed successfully.")
        else:
            logger.error("No markdown output generated.")
            sys.exit(1)
            
    except Exception as e:
        logger.exception("Error during OCR inference: %s", str(e))
        sys.exit(1)
    finally:
        # Clean up temporary directories
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

if __name__ == '__main__':
    main()
