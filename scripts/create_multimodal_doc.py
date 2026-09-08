"""Generates a multimodal PDF fixture containing real structured tables and embedded diagram figures."""

from pathlib import Path

import fitz
from PIL import Image, ImageDraw


def generate_architecture_diagram(output_path: Path) -> None:
    """Generates an architecture diagram image to embed in the PDF."""
    width, height = 750, 360
    img = Image.new("RGB", (width, height), color=(248, 250, 252))
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle([10, 10, width - 10, height - 10], outline=(203, 213, 225), width=2)

    # Title
    draw.text((30, 25), "HYBRID RAG MULTIMODAL INGESTION & RETRIEVAL PIPELINE", fill=(30, 41, 59))

    # Boxes
    boxes = [
        (35, 80, 165, 170, "Document PDF\n(Tables & Figs)", (59, 130, 246)),
        (195, 80, 345, 170, "Multimodal\nExtractor", (16, 185, 129)),
        (375, 80, 525, 170, "Dual Index\n(HNSW + BM25s)", (168, 85, 247)),
        (555, 80, 715, 170, "FlashRank CPU\nReranker", (245, 158, 11)),
    ]

    for x0, y0, x1, y1, label, color in boxes:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=color, outline=(255, 255, 255), width=2)
        draw.text((x0 + 15, y0 + 30), label, fill=(255, 255, 255))

    # Arrows
    arrows = [
        ((165, 125), (195, 125)),
        ((345, 125), (375, 125)),
        ((525, 125), (555, 125)),
    ]
    for start, end in arrows:
        draw.line([start, end], fill=(100, 116, 139), width=3)
        draw.polygon([(end[0], end[1]), (end[0] - 6, end[1] - 5), (end[0] - 6, end[1] + 5)], fill=(100, 116, 139))

    # Lower tier box (Local LLM Generation)
    draw.rounded_rectangle([195, 210, 525, 300], radius=8, fill=(15, 23, 42), outline=(59, 130, 246), width=2)
    draw.text((220, 240), "Local Ollama LLM (llama3.2:3b / bge-m3)\nUnder 6GB VRAM on RTX 3050", fill=(255, 255, 255))

    # Feedback arrow
    draw.line([(635, 170), (635, 255), (525, 255)], fill=(245, 158, 11), width=3)

    img.save(output_path)
    print(f"[+] Created architecture diagram image: {output_path}")


def create_multimodal_pdf(pdf_path: Path) -> None:
    doc = fitz.open()

    # --- PAGE 1: Hardware Benchmarks & Structured Table ---
    page1 = doc.new_page(width=612, height=792)  # Standard US Letter

    # Heading
    page1.insert_text((54, 60), "ENTERPRISE HYBRID RAG HARDWARE BENCHMARK SPECIFICATION", fontsize=15, fontname="helv", color=(0.1, 0.1, 0.2))
    page1.insert_text((54, 85), "Section 1: Hardware Execution Profiles and Latency Analysis", fontsize=12, fontname="helv", color=(0.2, 0.3, 0.5))

    intro_text = (
        "This specification establishes the latency, memory, and throughput performance characteristics "
        "of the localized hybrid retrieval system. All benchmarks were recorded using local quantization profiles "
        "running on consumer hardware without external cloud APIs."
    )
    page1.insert_textbox(fitz.Rect(54, 100, 558, 150), intro_text, fontsize=10, fontname="helv", color=(0.15, 0.15, 0.15))

    # Table 1 Caption
    page1.insert_text((54, 170), "Table 1: Hardware Latency & VRAM Benchmarks across Devices", fontsize=11, fontname="helv", color=(0.1, 0.1, 0.1))

    # Draw Structured Table 1
    # Columns: Device / GPU (120), Model (90), VRAM (60), Dense (65), Rerank (85), Throughput (70)
    t_x = 54
    t_y = 185
    col_widths = [130, 90, 60, 65, 85, 74]
    row_height = 24

    headers = ["Device / GPU", "Model Name", "VRAM", "Dense Latency", "Reranker", "Throughput"]
    rows = [
        ["RTX 3050 Laptop", "llama3.2:3b", "2.2 GB", "18.5 ms", "FlashRank CPU", "32.4 tok/s"],
        ["RTX 4060 Laptop", "llama3.1:8b", "5.4 GB", "12.1 ms", "FlashRank CPU", "45.2 tok/s"],
        ["Intel i7 CPU Core", "llama3.2:1b", "0.0 GB", "85.0 ms", "BM25s Lexical", "8.1 tok/s"],
        ["A100 TensorCore", "deepseek-r1:14b", "40.0 GB", "4.2 ms", "GPU Cross-Enc", "110.0 tok/s"],
    ]

    total_w = sum(col_widths)
    total_h = row_height * (len(rows) + 1)

    # Draw header background
    page1.draw_rect(fitz.Rect(t_x, t_y, t_x + total_w, t_y + row_height), color=(0.8, 0.85, 0.9), fill=(0.9, 0.93, 0.97))

    # Draw table border
    page1.draw_rect(fitz.Rect(t_x, t_y, t_x + total_w, t_y + total_h), color=(0.6, 0.6, 0.7), width=1)

    # Draw header cells
    curr_x = t_x
    for idx, h in enumerate(headers):
        w = col_widths[idx]
        page1.insert_text((curr_x + 6, t_y + 16), h, fontsize=9, fontname="helv", color=(0.1, 0.1, 0.2))
        page1.draw_line((curr_x, t_y), (curr_x, t_y + total_h), color=(0.7, 0.7, 0.8), width=0.5)
        curr_x += w
    page1.draw_line((curr_x, t_y), (curr_x, t_y + total_h), color=(0.7, 0.7, 0.8), width=0.5)

    # Draw row cells
    for r_idx, row in enumerate(rows):
        curr_y = t_y + (r_idx + 1) * row_height
        page1.draw_line((t_x, curr_y), (t_x + total_w, curr_y), color=(0.7, 0.7, 0.8), width=0.5)
        curr_x = t_x
        for c_idx, cell in enumerate(row):
            w = col_widths[c_idx]
            page1.insert_text((curr_x + 6, curr_y + 16), cell, fontsize=8.5, fontname="helv", color=(0.2, 0.2, 0.2))
            curr_x += w

    # Section 1 notes
    notes_text = (
        "Key takeaways from Table 1 demonstrate that FlashRank CPU reranking adds zero VRAM overhead, "
        "enabling high-accuracy cross-encoder scoring within a 6GB VRAM constraint. "
        "Dense vector retrieval operates at under 20ms using BGE-M3 embeddings in Qdrant."
    )
    page1.insert_textbox(fitz.Rect(54, t_y + total_h + 20, 558, 380), notes_text, fontsize=9.5, fontname="helv", color=(0.2, 0.2, 0.2))

    # --- PAGE 2: Architecture Figure & Multimodal Diagram ---
    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((54, 60), "Section 2: Pipeline Architecture and Component Topology", fontsize=14, fontname="helv", color=(0.1, 0.1, 0.2))

    p2_intro = (
        "The distributed pipeline decouples layout probing from chunking, indexing, and reranking. "
        "As illustrated in Figure 1, the Multimodal Extractor extracts both tabular matrixes and visual "
        "diagrams before passing normalized blocks to the dual vector and lexical indexers."
    )
    page2.insert_textbox(fitz.Rect(54, 80, 558, 140), p2_intro, fontsize=10, fontname="helv", color=(0.15, 0.15, 0.15))

    # Generate and embed diagram image
    diagram_img_path = Path("data/figures/temp_arch_diagram.png")
    diagram_img_path.parent.mkdir(parents=True, exist_ok=True)
    generate_architecture_diagram(diagram_img_path)

    # Insert Image on Page 2
    img_rect = fitz.Rect(54, 150, 558, 380)
    page2.insert_image(img_rect, filename=str(diagram_img_path))

    # Figure 1 Caption
    page2.insert_text((54, 400), "Figure 1: Hybrid RAG Ingestion and Cross-Encoder Reranking Architecture Flow", fontsize=10, fontname="helv", color=(0.1, 0.1, 0.2))

    fig_desc = (
        "Figure 1 illustrates the end-to-end data flow. The layout probe classifies documents and routes "
        "them to the Multimodal Extractor. Tables are exported as GitHub Markdown matrices, while figures "
        "are cropped as high-resolution PNGs. Both streams are indexed into Qdrant (dense) and BM25s (lexical) "
        "before being fused via RRF (k=60) and reranked via FlashRank CPU on consumer laptops."
    )
    page2.insert_textbox(fitz.Rect(54, 420, 558, 520), fig_desc, fontsize=9.5, fontname="helv", color=(0.2, 0.2, 0.2))

    # Save PDF
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(pdf_path))
    doc.close()
    print(f"[+] Created multimodal PDF: {pdf_path}")


if __name__ == "__main__":
    target = Path("data/documents/multimodal_hardware_benchmark.pdf")
    create_multimodal_pdf(target)
