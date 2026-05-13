from utils.text_cleaner import clean_text
from services.mongo_service import get_dataframe
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


def generate_insight():
    df = get_dataframe()

    if df.empty:
        return {"message": "No data"}

    df["clean_caption"] = df["caption"].apply(clean_text)

    df["date"] = pd.to_datetime(df["date"])

    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day"] = df["date"].dt.day_name()

    df["event_category"] = df["clean_caption"].apply(detect_event)

    insights = {
        "total_posts": len(df),

        "top_accounts":
            df["owner"].value_counts().head(5).to_dict(),

        "likes_distribution": {
            "min": int(df["likes"].min()),
            "max": int(df["likes"].max()),
            "avg": float(df["likes"].mean())
        },

        "most_active_day":
            df["day"].value_counts().to_dict(),

        "event_trends":
            df["event_category"].value_counts().to_dict()
    }

    return insights