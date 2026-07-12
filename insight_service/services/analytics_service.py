from ..utils.text_cleaner import clean_text
from .mongo_service import get_dataframe
import pandas as pd


EVENT_KEYWORDS = {
    "Natal": ["natal", "christmas"],
    "Paskah": ["paskah", "easter"],
    "Retreat": ["retreat"],
    "Youth": ["youth", "pemuda"],
    "Worship": ["worship", "penyembahan"],
    "Seminar": ["seminar", "conference"],
    "Kenaikan Yesus Kristus": ["kenaikan"]
}


def detect_event(text):
    text = str(text).lower()

    for event, keywords in EVENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return event

    return "Lainnya"


def generate_insight(date_from=None, date_to=None):
    df = get_dataframe()

    if df.empty:
        return {"message": "No data"}

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if date_from:
        df = df[df["date"] >= pd.to_datetime(date_from)]
    if date_to:
        df = df[df["date"] <= pd.to_datetime(date_to)]

    if df.empty:
        return {"message": "No data"}

    df["clean_caption"] = df["caption"].apply(clean_text)

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day"] = df["date"].dt.day_name()

    df["event_category"] = df["clean_caption"].apply(detect_event)

    likes = df["likes"].dropna()

    # Extract top keywords for word cloud
    word_counts = {}
    for caption in df["clean_caption"]:
        if caption:
            for word in caption.split():
                if len(word) > 3:
                    word_counts[word] = word_counts.get(word, 0) + 1
    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    word_cloud = [{"word": k, "count": int(v)} for k, v in top_words]

    insights = {
        "total_posts": len(df),

        "top_accounts":
            df["owner"].value_counts().head(5).to_dict(),

        "likes_distribution": {
            "min": int(likes.min()) if not likes.empty else 0,
            "max": int(likes.max()) if not likes.empty else 0,
            "avg": float(likes.mean()) if not likes.empty else 0.0
        },

        "most_active_day":
            df["day"].value_counts().to_dict(),

        "event_trends":
            df["event_category"].value_counts().to_dict(),

        "word_cloud": word_cloud
    }

    return insights