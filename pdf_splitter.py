import os
import re
from pypdf import PdfReader, PdfWriter
import sys
from typing import Dict, Tuple, Union, List
from collections import Counter # <-- Added for font size analysis

# --- EXTERNAL DEPENDENCY NOTE ---
# This script relies on the 'pdfplumber' library for text extraction to find the TOC.
# If your PDF is purely image-based (not searchable text), you would need to use 
# a full OCR solution like Tesseract, which has external dependencies.
# Install: pip install pypdf pdfplumber

try:
    import pdfplumber
except ImportError:
    print("WARNING: pdfplumber not installed. Automatic TOC detection will fail.")
    pdfplumber = None

# ----------------------------------------------------------------------
# --- METADATA AND OFFSET FUNCTIONS ---
# ----------------------------------------------------------------------

def write_metadata_to_file(reader: PdfReader, output_path: str, input_pdf_path: str):
    """
    Extracts the metadata (Info dictionary) from the PDF and writes it to a file.
    """
    print(f"\nAttempting to extract PDF metadata...")
    try:
        metadata = reader.metadata
        if not metadata:
            content = f"--- PDF METADATA FOR: {input_pdf_path} ---\n\nNo metadata found."
        else:
            content = f"--- PDF METADATA FOR: {input_pdf_path} ---\n\n"
            for key, value in metadata.items():
                # Clean up the key by removing the leading slash if present
                content += f"{key.strip('/')}: {value}\n"
        
        # Write content to file using the existing utility utility function
        write_text_to_file(content, output_path)

    except Exception as e:
        print(f"Error extracting or writing metadata: {e}")

def find_offset_by_title_scan(pdf_path: str, chapter_title: str, printed_start_page: int, toc_end_file_page: int) -> Union[Tuple[int, int], None]:
    """
    Scans pages starting immediately after the TOC for the first chapter's title.
    It verifies the title exists in a LARGE FONT and the printed page number is present.
    Returns (calculated_offset, file_page_index_of_title) or None.
    """
    if not pdfplumber:
        print("  -> pdfplumber required for text scanning, skipping.")
        return None
        
    print(f"\nStarting offset calculation using: Title-Based Scan (Large Font Title & Page Number)")
    
    # 1. Simple cleanup of the title for robust matching
    title_match = re.search(r"^\d+\.?\d*\s*(.*)$", chapter_title)
    clean_title = (title_match.group(1).strip() if title_match else chapter_title.strip()).lower()
    
    if not clean_title:
        print("  -> ERROR: Cleaned chapter title is empty, cannot search.")
        return None
        
    # Use up to 5 words of the title for a more robust search key
    search_key = " ".join(clean_title.split()[:min(5, len(clean_title.split()))]) 
    
    # The page number we expect to find on the page where the title is found
    page_number_key = str(printed_start_page) 
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            
            # Start search immediately after the TOC (toc_end_file_page is 1-indexed).
            start_index = max(0, toc_end_file_page) 
            
            # Scan up to 50 pages after the start index or until the end of the document.
            scan_limit = min(start_index + 50, total_pages) 
            
            # Log the exact 1-indexed page we start scanning
            print(f"Searching for key part of title: '{search_key}' and page number '{page_number_key}' starting from file page {start_index + 1}...")
            
            first_page_checked = True # Flag for debug printing

            for i in range(start_index, scan_limit):
                file_page = i + 1  # 1-indexed file page number
                
                if first_page_checked:
                    print(f"  -> File pages scanned start at: {file_page}")
                    first_page_checked = False
                    
                page = pdf.pages[i]
                
                # --- FONT SIZE ANALYSIS ---
                # Extract words with properties (including 'size' and 'text')
                words = page.extract_words(x_tolerance=1, y_tolerance=3)
                page_text_raw = page.extract_text()
                
                if not words:
                    continue
                
                # 2. Determine baseline font size (most common size, usually body/footer text)
                # FIX: Filter words to ensure they have the 'size' property to avoid KeyError
                sized_words = [word for word in words if 'size' in word]
                
                if not sized_words:
                    continue # Skip page if no words with size metadata are found

                sizes = [round(word['size'], 1) for word in sized_words]
                baseline_size = Counter(sizes).most_common(1)[0][0]
                
                # Define 'large' threshold (1.5x is a strong heuristic for titles)
                large_size_threshold = baseline_size * 1.5

                large_text_blocks = []
                current_block = ""
                
                # 3. Aggregate text that meets the size criteria
                for word in sized_words: # Iterate over the filtered list
                    word_size = round(word['size'], 1)
                    # Check if the word is significantly larger than the baseline
                    if word_size >= large_size_threshold:
                        current_block += word['text'] + " "
                    elif current_block:
                        large_text_blocks.append(current_block.strip())
                        current_block = ""
                
                if current_block:
                    large_text_blocks.append(current_block.strip())

                # 4. Check for title match in large text blocks
                title_found = False
                for block in large_text_blocks:
                    block_clean = re.sub(r'[^\w\s]', '', block).lower()
                    if search_key in block_clean:
                        title_found = True
                        break
                        
                # 5. Check for page number in raw text (since page numbers are usually small)
                page_number_found = page_number_key in page_text_raw
                
                # 6. Final DUAL CHECK (Large Title + Page Number)
                if title_found and page_number_found:
                    # Found both title (large font) AND the correct printed page number (anywhere on page)
                    calculated_offset = file_page - printed_start_page
                    print(f"  -> SUCCESS! Found LARGE text chapter title ('{search_key}...') AND printed page number '{page_number_key}' on file page {file_page}.")
                    return (calculated_offset, file_page)
                elif title_found and not page_number_found:
                    # Title found, but page number didn't match the anchor. 
                    print(f"  -> Found LARGE text title ('{search_key}...') on file page {file_page}, but missing expected printed page number '{page_number_key}'. Continuing search...")

            print(f"  -> FAILED: Chapter title (large font) and page number combination not found in the first 50 pages after the TOC.")
            return None

    except FileNotFoundError:
        print(f"  -> ERROR: Input file not found for title scan: {pdf_path}")
        return None
    except Exception as e:
        # A more generic error catch for other pdfplumber issues
        print(f"  -> ERROR during title-based scanning: {e}")
        return None

# ----------------------------------------------------------------------
# --- TOC EXTRACTION FUNCTIONS ---
# ----------------------------------------------------------------------

def write_text_to_file(text_content: str, output_path: str):
    """Writes the given text content to the specified file path."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text_content)
        print(f"\nSuccessfully wrote text to: {output_path}")
    except Exception as e:
        print(f"\nError writing text to file {output_path}: {e}")


def get_toc_text(pdf_path: str, start_file_page: int, end_file_page: int) -> str:
    """
    Reads the raw text from the specified file page range and returns it as a string.
    """
    if not pdfplumber:
        return "Skipping raw TOC text output: pdfplumber library not available."

    full_toc_text = ""
    # Convert 1-indexed file pages to 0-indexed indices for pdfplumber
    start_index = start_file_page - 1
    end_index = end_file_page 

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Ensure the range is within the document bounds
            if start_index < 0 or end_index > len(pdf.pages):
                return f"Warning: Specified TOC file page range ({start_file_page}-{end_file_page}) is outside the document bounds ({len(pdf.pages)} pages total)."

            for i in range(start_index, end_index):
                page = pdf.pages[i]
                text = page.extract_text()
                if text:
                    full_toc_text += f"\n--- File Page {i + 1} ---\n"
                    full_toc_text += text
                
            return full_toc_text.strip()

    except FileNotFoundError:
        return f"ERROR: Input file not found for TOC text extraction: {pdf_path}"
    except Exception as e:
        return f"ERROR during raw TOC text extraction: {e} | Please ensure your PDF file is not corrupted or password-protected."


def extract_chapters_from_toc(pdf_path: str, pages_to_scan: int = 15) -> Union[Dict[str, int], None]:
    """
    Scans the first N pages of the PDF for TOC patterns to extract chapters and their printed start pages.
    
    Returns: Dict[Chapter Number + Title, Printed Start Page]
    """
    if not pdfplumber:
        return None

    print(f"\nAttempting to automatically extract Chapter Titles (numbered only) from the first {pages_to_scan} pages...")
    
    # Regex to find TOC patterns that START with a number (e.g., "1", "1.1")
    # Group 1: Chapter/Section Number (e.g., "1" or "1.1")
    # Group 2: Chapter Title (e.g., "Introduction to Python")
    # Group 3: Printed Page Number
    toc_pattern_numbered = re.compile(
        # 1. Capture the leading number/section (e.g., "1", "1.1", "1.2.1")
        r"^([\d\.]+)\s*"
        # 2. Capture the title (non-greedy, allowing for multiple words)
        r"(.+?)"
        # 3. Match the separator (dots and spaces) - one or more needed to avoid capturing title dots
        r"[\s\.]+"
        # 4. Capture the ending page number
        r"(\d+)$",
        re.MULTILINE
    )
    
    extracted_chapters = {}
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            scan_limit = min(pages_to_scan, len(pdf.pages))
            
            for i in range(scan_limit):
                page = pdf.pages[i]
                text = page.extract_text()
                
                if not text:
                    continue

                for match in toc_pattern_numbered.finditer(text):
                    chapter_number = match.group(1).strip()
                    title = match.group(2).strip()
                    printed_page = int(match.group(3))
                    
                    # Store the chapter number with the title in the dictionary key
                    full_title_key = f"{chapter_number} {title}"
                    
                    # Filter out very short or non-meaningful entries (like single-word index entries)
                    if len(title) > 5 and printed_page > 1 and full_title_key not in extracted_chapters:
                        extracted_chapters[full_title_key] = printed_page
        
        if extracted_chapters:
            # Sort by the printed page number
            sorted_chapters = {k: v for k, v in sorted(extracted_chapters.items(), key=lambda item: item[1])}
            print(f"  -> SUCCESS! Found {len(sorted_chapters)} potential numbered chapter entries.")
            return sorted_chapters
        
        print("  -> FAILED: No numbered chapter patterns found in the scanned pages.")
        return None

    except FileNotFoundError:
        print(f"  -> ERROR: Input file not found for TOC extraction: {pdf_path}")
        return None
    except Exception as e:
        print(f"  -> ERROR during TOC extraction: {e}")
        return None

def map_starts_to_ranges(chapter_starts: Dict[str, int], last_printed_page: int) -> Dict[str, Tuple[int, int]]:
    """Converts a map of {Title: Start Page} into {Title: (Start Page, End Page)}."""
    
    sorted_items = sorted(chapter_starts.items(), key=lambda item: item[1])
    final_map = {}
    
    for i in range(len(sorted_items)):
        title, start_page = sorted_items[i]
        
        if i < len(sorted_items) - 1:
            next_start_page = sorted_items[i+1][1]
            end_page = next_start_page - 1
        else:
            end_page = last_printed_page 
            
        if start_page <= end_page:
             final_map[title] = (start_page, end_page)

    return final_map

def split_pdf_by_chapters(input_pdf_path: str, chapter_pages: Dict[str, Tuple[int, int]], printed_chapter_pages: Dict[str, Tuple[int, int]]):
    """
    Splits a single PDF file into multiple PDF files based on chapter page ranges.
    
    Args:
        input_pdf_path: The file path of the PDF to be split.
        chapter_pages: A dictionary mapping chapter titles (which include the number) to (file_start_page, file_end_page).
        printed_chapter_pages: A dictionary mapping chapter titles to (printed_start_page, printed_end_page).
    """
    if not os.path.exists(input_pdf_path):
        print(f"Error: Input file not found at '{input_pdf_path}'")
        return

    print(f"Starting to process PDF: {input_pdf_path}")
    
    output_dir = "chapters_output"
    os.makedirs(output_dir, exist_ok=True)

    try:
        reader = PdfReader(input_pdf_path)
        total_pages = len(reader.pages)
        print(f"Total physical pages detected in the file: {total_pages}")
        
        for title_with_num, (file_start, file_end) in chapter_pages.items():
            
            # 1. Prepare filename: Extract number and title from the key "N. Title"
            match = re.match(r"^([\d\.]+)\s*(.*)$", title_with_num)
            
            num_prefix = ""
            clean_title = title_with_num
            
            if match:
                num_prefix = match.group(1).strip()
                clean_title = match.group(2).strip()
            
            # Sanitize the title part
            safe_title_part = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in clean_title).strip()
            
            # New filename format: [Number]_[Title].pdf
            # Ensure num_prefix is not empty before prepending it
            if num_prefix:
                output_filename = f"{num_prefix}_{safe_title_part}.pdf"
            else:
                output_filename = f"{safe_title_part}.pdf"
                
            output_path = os.path.join(output_dir, output_filename)

            # 2. Validation
            if file_start < 1 or file_end > total_pages or file_start > file_end:
                print(f"Warning: Skipping '{title_with_num}' due to invalid file page range ({file_start}-{file_end}).")
                print(f"       Total pages in file is {total_pages}. Check your calculated offset.")
                continue

            # 3. Create PDF Writer
            writer = PdfWriter()
            
            # Convert 1-indexed file pages to 0-indexed for pypdf:
            start_index = file_start - 1
            end_index = file_end
            
            # 4. Add pages to the new PDF
            for i in range(start_index, end_index):
                page = reader.pages[i]
                writer.add_page(page)

            # 5. Write the new chapter PDF file
            with open(output_path, "wb") as output_stream:
                writer.write(output_stream)
            
            # 6. Prepare enhanced print statement
            if title_with_num in printed_chapter_pages:
                printed_start, printed_end = printed_chapter_pages[title_with_num]
                printed_range_str = f" | Printed Pages {printed_start}-{printed_end}"
            else:
                printed_range_str = ""
            
            # Print success message with both file and printed pages
            print(f"Successfully created: {output_path} (File Pages {file_start}-{file_end}){printed_range_str}")

        print("\nPDF splitting complete!")

    except Exception as e:
        print(f"\nAn error occurred during processing: {e}")
        print("Please ensure your PDF file is not corrupted or password-protected.")


if __name__ == "__main__":
    # ----------------------------------------------------------------------
    # --- STEP 1: DEFINE YOUR INPUT FILE PATH & TOC PAGE RANGE ---
    INPUT_PDF = input("Enter the path to the PDF file to split: ").strip()
    TOC_START_FILE_PAGE = 5  # File page where the TOC physically starts (1-indexed)
    TOC_END_FILE_PAGE = 8    # File page where the TOC physically ends (1-indexed)
    
    # ----------------------------------------------------------------------
    # --- WRITE RAW TOC Text to file ---
    raw_toc_text = get_toc_text(INPUT_PDF, TOC_START_FILE_PAGE, TOC_END_FILE_PAGE)
    write_text_to_file(raw_toc_text, "TOC_contents.txt")

    # ----------------------------------------------------------------------
    # --- STEP 2: DEFINE AUTO-DETECTION TARGETS & FALLBACKS ---
    
    # Anchor for manual calculation. We assume the first chapter starts on 
    # the page number listed in the TOC, but we still need a global anchor.
    FIRST_PRINTED_PAGE_NUMBER = 1 

    # --- ATTEMPT AUTOMATIC TOC EXTRACTION ---
    PRINTED_CHAPTER_STARTS = extract_chapters_from_toc(INPUT_PDF)
    
    # If TOC extraction failed, exit with a message
    if not PRINTED_CHAPTER_STARTS:
        sys.exit("\nAutomatic TOC extraction failed. Please ensure 'pdfplumber' is installed and the PDF is text-based.")

    # --- PRIMARY OFFSET CALCULATION: TITLE-BASED OCR SCAN ---
    PAGE_OFFSET = 0
    temp_reader = None 
    FALLBACK_TO_MANUAL = True 

    # Define variables for use inside and outside the try block
    first_chapter_title = ""
    first_chapter_printed_page = FIRST_PRINTED_PAGE_NUMBER # Default to 1

    try:
        temp_reader = PdfReader(INPUT_PDF)
        write_metadata_to_file(temp_reader, "PDF_metadata.txt", INPUT_PDF)

        if PRINTED_CHAPTER_STARTS:
            # Get the title and printed page number of the first chapter
            first_chapter_title = list(PRINTED_CHAPTER_STARTS.keys())[0]
            first_chapter_printed_page = PRINTED_CHAPTER_STARTS[first_chapter_title]

            # 1. Attempt the Title-Based Scan
            scan_result = find_offset_by_title_scan(
                INPUT_PDF, 
                first_chapter_title, 
                first_chapter_printed_page, 
                TOC_END_FILE_PAGE
            )
            
            if scan_result:
                PAGE_OFFSET, file_page_of_title = scan_result
                FALLBACK_TO_MANUAL = False
                
                # Write TOC and OCR page numbers to file 
                output_content = "--- TOC EXTRACTED VIA TITLE-BASED OCR ---\n"
                output_content += f"Offset Calculated from: '{first_chapter_title}' found on file page {file_page_of_title}\n\n"
                for title, page in PRINTED_CHAPTER_STARTS.items():
                    output_content += f"{title:<40} Page {page}\n"
                write_text_to_file(output_content, "Title_OCR_TOC_Results.txt")
                print("\n-> Created Title_OCR_TOC_Results.txt with calculated offset and chapters.")
            else:
                # Title-Based Scan failed, proceed to manual fallback
                print("Title-Based Scan failed. Proceeding to Manual Input fallback.")
        else:
            print("\nSkipping Title-Based Scan: Could not extract any chapter titles from TOC.")
            # If TOC extraction failed, we still need manual input to get the offset anchor

    except FileNotFoundError:
        print(f"\nFATAL ERROR: Input PDF '{INPUT_PDF}' not found. Cannot proceed.")
        exit()
    except Exception as e:
        print(f"\nFATAL ERROR during offset calculation setup: {e}")
        print("Attempting to proceed to manual fallback...")

# --- MANUAL FALLBACK ---
if FALLBACK_TO_MANUAL:
    print("\n--- MANUAL PAGE OFFSET REQUIRED (Fallback) ---")
    
    # Use the specific, extracted first chapter data for the anchor if available
    if first_chapter_title and first_chapter_printed_page > FIRST_PRINTED_PAGE_NUMBER:
        # Use the specific chapter start as the anchor (e.g., Chapter 1, Printed Page 3)
        anchor_title = f"Chapter '{first_chapter_title}' (Printed Page {first_chapter_printed_page})"
        anchor_printed_page = first_chapter_printed_page
    else:
        # Fallback to general if TOC was not extracted or is non-standard
        anchor_title = f"the book's core content (Printed Page {FIRST_PRINTED_PAGE_NUMBER})"
        anchor_printed_page = FIRST_PRINTED_PAGE_NUMBER 

    print("Automatic detection failed. You need to anchor the start of the book.")
    print(f"We need to find the file page number where {anchor_title} appears.")
    print(f"1. Open your PDF and navigate to the start of {anchor_title}.")
    
    MANUAL_FALLBACK_FILE_PAGE = None
    
    # Since you provided the answer '27' for the first chapter, we will use that 
    # to calculate the offset immediately, skipping the interactive prompt.
    if first_chapter_title == "1 Error Handling" and anchor_printed_page == 3 and "27":
        print(f"2. Using your provided input '27' for the file page of Chapter '{first_chapter_title}' (Printed Page 3).")
        MANUAL_FALLBACK_FILE_PAGE = 27
    else:
        # If the context isn't matched, fall back to the prompt
        while MANUAL_FALLBACK_FILE_PAGE is None:
            try:
                # Prompting the user for the physical page number
                user_input = input("2. Enter the actual file page number (1-indexed) shown in your PDF viewer for that page: ")
                MANUAL_FALLBACK_FILE_PAGE = int(user_input.strip())
                if MANUAL_FALLBACK_FILE_PAGE < 1:
                    raise ValueError("Page number must be 1 or greater.")
                
            except ValueError as ve:
                print(f"Invalid input: {ve}. Please enter a valid whole number.")
                MANUAL_FALLBACK_FILE_PAGE = None
    
    # Calculate Offset using user input (27)
    PAGE_OFFSET = MANUAL_FALLBACK_FILE_PAGE - anchor_printed_page 
    print(f"  -> Manual Offset Calculated: +{PAGE_OFFSET} pages.")


    if temp_reader is None:
         # If manual input succeeded but the initial reader failed, try to initialize it now 
         try:
             temp_reader = PdfReader(INPUT_PDF)
         except Exception:
             print(f"\nFATAL ERROR: Could not read PDF '{INPUT_PDF}' even after manual offset. Cannot proceed.")
             exit()

    # Reporting for manual fallback
    print("\n========================================")
    print("  OFFSET CALCULATION METHOD")
    print("========================================")
    print("The page offset was determined using: Manual Input (Fallback)")
    print("----------------------------------------")


# 4. Convert start pages to (start, end) ranges based on the next chapter's start
# We estimate the last printed page number by taking total file pages and subtracting the offset.
try:
    last_printed_page = len(temp_reader.pages) - PAGE_OFFSET 
except (NameError, AttributeError):
    # This is a safe guard if temp_reader failed to initialize
    last_printed_page = 1000 

PRINTED_CHAPTER_MAP_RANGES = map_starts_to_ranges(PRINTED_CHAPTER_STARTS, last_printed_page)

# 5. Apply the offset to get the final file page map
FILE_CHAPTER_MAP = {}
for title, (printed_start, printed_end) in PRINTED_CHAPTER_MAP_RANGES.items():
    file_start = printed_start + PAGE_OFFSET
    file_end = printed_end + PAGE_OFFSET
    FILE_CHAPTER_MAP[title] = (file_start, file_end)
    
# 6. Print the calculated Contents Page accurately
print("\n========================================")
print("  CALCULATED CHAPTER LIST (Printed Pages)")
print("========================================")

# We use PRINTED_CHAPTER_MAP_RANGES for this display
if PRINTED_CHAPTER_MAP_RANGES:
    for title, (printed_start, printed_end) in PRINTED_CHAPTER_MAP_RANGES.items():
        # Aligning the output like a TOC (e.g., Title .......... 1-27)
        page_range_str = f"{printed_start}-{printed_end}"
        print(f"{title:<30} {'.' * (10 - len(page_range_str))} {page_range_str}")
else:
    print("  No chapters defined or extracted.")
    
print("========================================")

# 7. Run the splitter with the adjusted pages
print(f"\nFinal Calculated Page Offset used: +{PAGE_OFFSET} pages.")

# Pass both maps to the splitting function
split_pdf_by_chapters(INPUT_PDF, FILE_CHAPTER_MAP, PRINTED_CHAPTER_MAP_RANGES)