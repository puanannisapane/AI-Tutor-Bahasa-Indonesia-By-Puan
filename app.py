import streamlit as st
from pathlib import Path
from collections import Counter
import math
import re
import html


# =========================================================
# KONFIGURASI APLIKASI
# =========================================================

st.set_page_config(
    page_title="AI Tutor Bahasa Indonesia",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

FOLDER_DATABASE = Path(__file__).resolve().parent / "database"
MAX_FILE_SIZE_MB = 5


# =========================================================
# STYLE
# =========================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.35rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }

    .subtitle {
        color: #6b7280;
        font-size: 1.02rem;
        margin-bottom: 1.2rem;
    }

    .source-card {
        padding: 0.9rem 1rem;
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 12px;
        margin-bottom: .7rem;
    }

    .small-muted {
        color: #6b7280;
        font-size: .85rem;
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.2);
        padding: .75rem;
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# STOPWORDS
# =========================================================

STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "pada", "dengan", "untuk",
    "dalam", "adalah", "itu", "ini", "atau", "apa", "bagaimana",
    "mengapa", "sebutkan", "jelaskan", "jelaskanlah", "tentang",
    "suatu", "sebuah", "secara", "merupakan", "dapat", "akan",
    "sebagai", "oleh", "lebih", "juga", "tidak", "tersebut",
    "yaitu", "yakni", "saja", "karena", "agar", "dalam", "kepada",
    "bagi", "jadi", "serta", "saat", "sudah", "telah", "masih",
    "bisa", "buat", "cara", "fungsi", "jenis", "contoh", "jelaskan",
}


# =========================================================
# FUNGSI TEKS
# =========================================================

def bersihkan_teks(teks: str) -> str:
    """Normalisasi teks untuk proses pencarian."""
    teks = str(teks).lower()
    teks = re.sub(r"[^\w\s-]", " ", teks, flags=re.UNICODE)
    teks = re.sub(r"[_-]+", " ", teks)
    teks = re.sub(r"\s+", " ", teks)
    return teks.strip()


def tokenisasi(teks: str) -> list[str]:
    """Mengambil token/kata yang cukup informatif."""
    bersih = bersihkan_teks(teks)
    return [
        kata for kata in bersih.split()
        if len(kata) >= 3 and kata not in STOPWORDS
    ]


def format_nama_file(nama_file: str) -> str:
    nama = Path(nama_file).stem.replace("_", " ").replace("-", " ")
    return nama.title()


def hitung_kata(teks: str) -> int:
    return len(teks.split())


def ambil_paragraf(teks: str) -> list[str]:
    """Memisahkan isi database menjadi paragraf yang masuk akal."""
    bagian = re.split(r"\n\s*\n+", teks.strip())
    if len(bagian) == 1:
        bagian = re.split(r"\n+", teks.strip())
    return [p.strip() for p in bagian if p.strip()]


# =========================================================
# DATABASE
# =========================================================

@st.cache_data(show_spinner=False)
def baca_database():
    """
    Membaca seluruh TXT dari folder database, termasuk subfolder.
    Cache digunakan agar aplikasi lebih cepat saat pertanyaan berulang.
    """
    FOLDER_DATABASE.mkdir(parents=True, exist_ok=True)

    data = []

    for lokasi_file in sorted(FOLDER_DATABASE.rglob("*.txt")):
        try:
            ukuran_mb = lokasi_file.stat().st_size / (1024 * 1024)

            if ukuran_mb > MAX_FILE_SIZE_MB:
                data.append({
                    "nama_file": lokasi_file.name,
                    "path": str(lokasi_file.relative_to(FOLDER_DATABASE)),
                    "isi": "",
                    "error": (
                        f"File terlalu besar ({ukuran_mb:.1f} MB). "
                        f"Maksimal {MAX_FILE_SIZE_MB} MB."
                    ),
                    "kata": 0,
                })
                continue

            isi = lokasi_file.read_text(encoding="utf-8", errors="replace").strip()

            data.append({
                "nama_file": lokasi_file.name,
                "path": str(lokasi_file.relative_to(FOLDER_DATABASE)),
                "isi": isi,
                "error": "",
                "kata": hitung_kata(isi),
            })

        except Exception as error:
            data.append({
                "nama_file": lokasi_file.name,
                "path": str(lokasi_file.relative_to(FOLDER_DATABASE)),
                "isi": "",
                "error": str(error),
                "kata": 0,
            })

    return data


# =========================================================
# MESIN PENCARIAN
# =========================================================

def skor_dokumen(pertanyaan: str, dokumen: dict) -> tuple[float, dict]:
    """
    Menghitung relevansi menggunakan beberapa sinyal:
    - kecocokan kata kunci
    - cakupan kata kunci
    - frekuensi kata
    - kecocokan nama/judul file
    - kecocokan frasa pertanyaan
    """
    if not dokumen["isi"]:
        return 0.0, {}

    query_tokens = tokenisasi(pertanyaan)
    query_unique = list(dict.fromkeys(query_tokens))

    if not query_unique:
        return 0.0, {}

    isi_bersih = bersihkan_teks(dokumen["isi"])
    nama_bersih = bersihkan_teks(Path(dokumen["nama_file"]).stem)
    frekuensi = Counter(isi_bersih.split())

    cocok = []
    total = 0.0

    for kata in query_unique:
        jumlah = frekuensi.get(kata, 0)
        if jumlah > 0:
            cocok.append(kata)
            # Frekuensi tambahan diberi bobot log agar dokumen
            # tidak menang hanya karena kata diulang berkali-kali.
            total += 3.0 + min(math.log1p(jumlah), 3.0)

            if kata in nama_bersih.split():
                total += 6.0

    coverage = len(cocok) / len(query_unique)
    total += coverage * 12.0

    pertanyaan_bersih = bersihkan_teks(pertanyaan)
    if len(pertanyaan_bersih) >= 8 and pertanyaan_bersih in isi_bersih:
        total += 15.0

    # Bonus jika beberapa kata kunci muncul berdekatan.
    query_phrase = " ".join(query_unique[:4])
    if len(query_phrase) >= 8 and query_phrase in isi_bersih:
        total += 8.0

    detail = {
        "cocok": cocok,
        "coverage": coverage,
        "jumlah_kata_kunci": len(query_unique),
    }

    return total, detail


def cari_materi(pertanyaan: str, database: list[dict]) -> list[dict]:
    hasil = []

    for dokumen in database:
        skor, detail = skor_dokumen(pertanyaan, dokumen)

        if skor > 0:
            hasil.append({
                **dokumen,
                "skor": skor,
                "detail": detail,
            })

    hasil.sort(key=lambda item: item["skor"], reverse=True)
    return hasil


# =========================================================
# MENGAMBIL JAWABAN DARI MATERI
# =========================================================

def skor_paragraf(pertanyaan: str, paragraf: str) -> int:
    kata_kunci = set(tokenisasi(pertanyaan))
    paragraf_bersih = bersihkan_teks(paragraf)
    token_paragraf = paragraf_bersih.split()

    if not kata_kunci or not token_paragraf:
        return 0

    frekuensi = Counter(token_paragraf)
    skor = 0

    for kata in kata_kunci:
        if kata in frekuensi:
            skor += 1
            if frekuensi[kata] >= 3:
                skor += 1

    return skor


def ambil_jawaban(pertanyaan: str, isi: str, mode: str = "Ringkas") -> str:
    paragraf = ambil_paragraf(isi)

    if not paragraf:
        return "Materi ditemukan, tetapi isinya kosong."

    berperingkat = [
        (skor_paragraf(pertanyaan, p), i, p)
        for i, p in enumerate(paragraf)
    ]

    berperingkat.sort(key=lambda x: (x[0], -x[1]), reverse=True)

    batas = 1800 if mode == "Ringkas" else 3500
    terpilih = []
    panjang = 0

    # Jika ada kecocokan, prioritaskan paragraf paling relevan.
    kandidat = [item for item in berperingkat if item[0] > 0]

    # Jika tidak ada paragraf yang cocok, ambil bagian awal materi.
    if not kandidat:
        hasil = "\n\n".join(paragraf)
        return hasil[:batas].strip()

    for skor, indeks, paragraf_item in kandidat:
        tambahan = len(paragraf_item) + (2 if terpilih else 0)

        if panjang + tambahan <= batas:
            terpilih.append((indeks, paragraf_item))
            panjang += tambahan

    # Kembalikan sesuai urutan asli agar penjelasan tetap runtut.
    terpilih.sort(key=lambda x: x[0])
    jawaban = "\n\n".join(p for _, p in terpilih)

    return jawaban.strip()


def buat_saran(pertanyaan: str, database: list[dict], jumlah: int = 5) -> list[str]:
    """
    Memberikan saran berdasarkan kata kunci yang ditemukan pada
    nama file database.
    """
    query_tokens = set(tokenisasi(pertanyaan))
    skor_saran = []

    for dokumen in database:
        nama_tokens = set(tokenisasi(Path(dokumen["nama_file"]).stem))
        cocok = len(query_tokens & nama_tokens)
        if cocok:
            skor_saran.append((cocok, format_nama_file(dokumen["nama_file"])))

    skor_saran.sort(reverse=True)
    return [nama for _, nama in skor_saran[:jumlah]]


# =========================================================
# SESSION STATE
# =========================================================

if "riwayat" not in st.session_state:
    st.session_state.riwayat = []

if "pertanyaan_terakhir" not in st.session_state:
    st.session_state.pertanyaan_terakhir = ""


# =========================================================
# LOAD DATABASE
# =========================================================

database = baca_database()
database_valid = [d for d in database if d["isi"]]
database_error = [d for d in database if d["error"]]


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.header("📖 Knowledge Base")

    st.metric("Materi TXT", len(database_valid))
    total_kata = sum(d["kata"] for d in database_valid)
    st.metric("Total kata", f"{total_kata:,}".replace(",", "."))

    st.divider()

    st.subheader("⚙️ Pengaturan")

    mode_jawaban = st.radio(
        "Panjang jawaban",
        ["Ringkas", "Detail"],
        index=0,
    )

    jumlah_terkait = st.slider(
        "Materi terkait",
        min_value=1,
        max_value=5,
        value=3,
    )

    st.divider()

    if st.button("🔄 Muat ulang database", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    if st.button("🗑️ Hapus riwayat", use_container_width=True):
        st.session_state.riwayat = []
        st.session_state.pertanyaan_terakhir = ""
        st.rerun()

    with st.expander("📚 Daftar materi", expanded=False):
        if database_valid:
            for dokumen in database_valid:
                st.write(f"📄 {format_nama_file(dokumen['nama_file'])}")
        else:
            st.warning("Belum ada file TXT di folder database.")

    if database_error:
        with st.expander("⚠️ File bermasalah", expanded=False):
            for dokumen in database_error:
                st.error(f"{dokumen['path']}: {dokumen['error']}")


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="main-title">📚 AI Tutor Bahasa Indonesia</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    "Tutor pembelajaran berbasis Knowledge Base TXT. "
    "Jawaban diambil dari materi yang tersimpan di folder database."
    "</div>",
    unsafe_allow_html=True,
)

tab_tanya, tab_database, tab_tentang = st.tabs(
    ["💬 Tanya Tutor", "📚 Knowledge Base", "ℹ️ Tentang"]
)


# =========================================================
# TAB TANYA
# =========================================================

with tab_tanya:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Materi tersedia", len(database_valid))

    with col2:
        st.metric("Total kata", f"{total_kata:,}".replace(",", "."))

    with col3:
        st.metric("Pertanyaan", len(st.session_state.riwayat))

    st.divider()

    # Tampilkan riwayat percakapan.
    for item in st.session_state.riwayat:
        with st.chat_message("user"):
            st.write(item["pertanyaan"])

        with st.chat_message("assistant"):
            st.write(item["jawaban"])
            st.caption(
                f"Sumber: {item['sumber']} • "
                f"Skor relevansi: {item['skor']:.1f}"
            )

    pertanyaan = st.chat_input(
        "Contoh: Apa yang dimaksud dengan kalimat efektif?"
    )

    # Dukungan tombol pertanyaan terakhir jika user tidak memakai chat_input.
    if pertanyaan:
        st.session_state.pertanyaan_terakhir = pertanyaan

    if pertanyaan:
        if not database_valid:
            st.error(
                "Database belum tersedia. Pastikan folder "
                "`database/` berisi file `.txt`."
            )
        else:
            with st.spinner("🔎 Mencari materi yang paling relevan..."):
                hasil = cari_materi(pertanyaan, database_valid)

            if hasil:
                utama = hasil[0]
                jawaban = ambil_jawaban(
                    pertanyaan,
                    utama["isi"],
                    mode_jawaban,
                )

                st.session_state.riwayat.append({
                    "pertanyaan": pertanyaan,
                    "jawaban": jawaban,
                    "sumber": utama["nama_file"],
                    "skor": utama["skor"],
                })

                st.rerun()

            else:
                saran = buat_saran(pertanyaan, database_valid)

                st.warning(
                    "Materi yang cukup relevan belum ditemukan dalam database."
                )

                if saran:
                    st.info(
                        "Coba gunakan topik yang lebih spesifik, misalnya: "
                        + ", ".join(saran)
                    )

    # Alternatif form untuk pengguna yang lebih nyaman dengan tombol.
    with st.expander("✍️ Form pertanyaan"):
        with st.form("form_pertanyaan"):
            pertanyaan_form = st.text_area(
                "Tulis pertanyaan:",
                height=100,
                placeholder="Contoh: Jelaskan pengertian morfologi.",
            )
            kirim = st.form_submit_button(
                "🔍 Cari Jawaban",
                use_container_width=True,
            )

        if kirim:
            if not pertanyaan_form.strip():
                st.warning("Silakan masukkan pertanyaan.")
            elif not database_valid:
                st.error("Database TXT belum ditemukan.")
            else:
                hasil = cari_materi(pertanyaan_form, database_valid)

                if hasil:
                    utama = hasil[0]
                    jawaban = ambil_jawaban(
                        pertanyaan_form,
                        utama["isi"],
                        mode_jawaban,
                    )

                    st.session_state.riwayat.append({
                        "pertanyaan": pertanyaan_form,
                        "jawaban": jawaban,
                        "sumber": utama["nama_file"],
                        "skor": utama["skor"],
                    })
                    st.rerun()
                else:
                    st.warning("Materi yang relevan belum ditemukan.")


# =========================================================
# TAB DATABASE
# =========================================================

with tab_database:
    st.subheader("📚 Materi dalam Knowledge Base")

    if database_valid:
        for dokumen in database_valid:
            with st.expander(
                f"📄 {format_nama_file(dokumen['nama_file'])}"
            ):
                col_a, col_b = st.columns(2)

                with col_a:
                    st.write(f"**File:** `{dokumen['path']}`")

                with col_b:
                    st.write(f"**Jumlah kata:** {dokumen['kata']:,}".replace(",", "."))

                st.text_area(
                    "Isi materi",
                    value=dokumen["isi"],
                    height=220,
                    key=f"preview_{dokumen['path']}",
                )

                st.download_button(
                    "⬇️ Unduh materi",
                    data=dokumen["isi"],
                    file_name=dokumen["nama_file"],
                    mime="text/plain",
                    key=f"download_{dokumen['path']}",
                )
    else:
        st.info(
            "Belum ada materi. Buat folder `database` dan masukkan "
            "file `.txt` ke dalamnya."
        )


# =========================================================
# TAB TENTANG
# =========================================================

with tab_tentang:
    st.subheader("ℹ️ Tentang Aplikasi")

    st.write(
        """
        **AI Tutor Bahasa Indonesia** adalah aplikasi pembelajaran yang
        menggunakan file TXT sebagai Knowledge Base. Pengguna dapat
        mengajukan pertanyaan, kemudian sistem mencari materi yang paling
        relevan berdasarkan kata kunci, kecocokan judul file, frekuensi kata,
        dan kecocokan frasa.
        """
    )

    st.info(
        "Catatan: aplikasi ini tidak menggunakan API AI eksternal. "
        "Jawaban berasal dari materi TXT yang tersedia di folder database."
    )

    st.markdown("### Struktur folder")
    st.code(
        """Pemrograman Pembelajaran AI/
├── app.py
├── requirements.txt
└── database/
    ├── materi1.txt
    ├── materi2.txt
    └── materi_lainnya.txt
""",
        language="text",
    )


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "AI Tutor Bahasa Indonesia • Python + Streamlit + TXT Knowledge Base"
)
