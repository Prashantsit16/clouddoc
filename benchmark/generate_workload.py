import os
import fitz  # PyMuPDF

def generate_pdf(filepath: str, num_pages: int, title: str):
    doc = fitz.open()
    for page_num in range(1, num_pages + 1):
        page = doc.new_page(width=595, height=842)  # A4 size
        rect = fitz.Rect(50, 50, 545, 100)
        page.insert_textbox(rect, f"{title} - Page {page_num} of {num_pages}", fontsize=16, fontname="helv", color=(0.1, 0.2, 0.4))
        
        body_text = "\n\n".join([
            f"Section {page_num}.{i}: CloudDoc Asynchronous Processing Performance Benchmark. "
            f"CloudDoc processes documents using an event-driven architecture with AWS S3, SQS, and detached workers. "
            f"This synthetic content provides realistic text density for PyMuPDF text extraction parsing."
            for i in range(1, 8)
        ])
        body_rect = fitz.Rect(50, 120, 545, 800)
        page.insert_textbox(body_rect, body_text, fontsize=10, fontname="helv")
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc.save(filepath)
    doc.close()
    file_size_kb = os.path.getsize(filepath) / 1024
    print(f"Generated {filepath} ({num_pages} pages, {file_size_kb:.2f} KB)")
    return filepath

if __name__ == "__main__":
    workload_dir = os.path.join(os.path.dirname(__file__), "workload")
    generate_pdf(os.path.join(workload_dir, "small_1p.pdf"), num_pages=1, title="CloudDoc Benchmark Small PDF")
    generate_pdf(os.path.join(workload_dir, "medium_5p.pdf"), num_pages=5, title="CloudDoc Benchmark Medium PDF")
    generate_pdf(os.path.join(workload_dir, "large_20p.pdf"), num_pages=20, title="CloudDoc Benchmark Large PDF")
