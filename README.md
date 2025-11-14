# PDF Chapter Splitter

A Python script that automatically splits PDF files into individual chapter files based on the table of contents.

## Features

- **Automatic TOC Extraction**: Scans the first pages of a PDF to detect numbered chapters and their page numbers
- **Smart Offset Detection**: Uses font size analysis and title matching to calculate page number offsets between printed and file pages
- **Metadata Extraction**: Saves PDF metadata and TOC contents to text files for reference
- **Manual Fallback**: Prompts for manual input if automatic detection fails

## Requirements

```bash
pip install -r requirements.txt
```

## Usage

1. Run the script:
```bash
python pdf_splitter.py
```

2. Enter the path to your PDF when prompted

3. Configure TOC page range in the script (default: pages 5-8):
```python
TOC_START_FILE_PAGE = 5
TOC_END_FILE_PAGE = 8
```

4. The script will automatically:
   - Extract chapter titles and page numbers from the TOC
   - Calculate the page offset using font analysis
   - Split the PDF into individual chapter files

## Output

- **chapters_output/**: Folder containing individual chapter PDFs named `[Number]_[Title].pdf`
- **TOC_contents.txt**: Raw text extracted from the TOC pages
- **PDF_metadata.txt**: PDF metadata information
- **Title_OCR_TOC_Results.txt**: Calculated offset and chapter list (if auto-detection succeeds)

## How It Works

1. Extracts numbered chapters from the TOC using regex patterns
2. Scans pages after the TOC for the first chapter title in large font
3. Verifies the printed page number appears on the same page
4. Calculates the offset between printed and file page numbers
5. Splits the PDF based on calculated chapter ranges

## Limitations

- Requires text-based PDFs (not scanned images without OCR)
- Only extracts numbered chapters (e.g., "1 Introduction", "2.1 Methods")
- TOC must follow standard patterns with chapter numbers and page numbers

## Troubleshooting

If automatic detection fails, the script will prompt for manual input. Simply open the PDF and enter the file page number where the first chapter begins.