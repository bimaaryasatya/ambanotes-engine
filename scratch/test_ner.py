from transformers import pipeline

text = "SURAT KESEPAKATAN BIMBINGAN PENGABDIAN PADA MASYARAKAT Kami yang bertanda tangan di bawah ini : Pihak Pertama NO NIM Nama 1 Bima Sunu Aryasatya 23090043 2 Geraldi Novalino Putra 23090002 3 Putra Nur Izzatul Ramadhan 23090114 4 Yusuf Dwi Saputra 23090127 Pihak Kedua Nama : Dairoh, S.Si., M.Sc."

try:
    print("Loading model...")
    ner_pipeline = pipeline("ner", model="cahya/bert-base-indonesian-NER-1", aggregation_strategy="simple")
    print("Extracting...")
    entities = ner_pipeline(text)
    for ent in entities:
        print(ent)
except Exception as e:
    print(f"Error: {e}")
