import json
import logging
import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

logging.basicConfig(level=logging.INFO)
app = Flask(__name__, static_folder="static", static_url_path="/static")

PLATFORM_RULES = {
    "LinkedIn": "professional hook in the first line, short paragraphs, 120 to 220 words, ends with a question or call to action, 3 to 5 hashtags",
    "Instagram": "engaging caption with a strong first line, light emoji use, line breaks, a call to action, 8 to 15 hashtags",
    "X": "maximum 280 characters INCLUDING hashtags, punchy, 1 to 2 hashtags",
    "Facebook": "friendly and conversational, 40 to 100 words, ends with a question that invites comments, 1 to 3 hashtags",
}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


@app.errorhandler(ApiError)
def handle_api_error(e):
    return jsonify(error=e.message), e.status


def text(data, key, limit):
    return str(data.get(key, "")).strip()[:limit]


def pick_platforms(data):
    chosen = [p for p in data.get("platforms", []) if p in PLATFORM_RULES]
    if not chosen:
        raise ApiError("Choose at least one platform.")
    return chosen


def rules_for(platforms):
    return "\n".join(f"- {p}: {PLATFORM_RULES[p]}" for p in platforms)


def ask(system, user, max_tokens=2200):
    """Call OpenRouter and return the parsed JSON object from the reply."""
    if not API_KEY:
        raise ApiError("Server is missing OPENROUTER_API_KEY. Check your .env file.", 500)
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:5000",
        "X-Title": "AI Social Media Automation Tool",
    }
    try:
        r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        start, end = content.find("{"), content.rfind("}")
        return json.loads(content[start : end + 1])
    except requests.Timeout:
        raise ApiError("The AI took too long. Please try again.", 504)
    except requests.HTTPError as e:
        logging.error("OpenRouter %s: %s", e.response.status_code, e.response.text[:300])
        raise ApiError("The AI service returned an error. Check your API key and model.", 502)
    except (ValueError, KeyError, IndexError, AttributeError, TypeError) as e:
        logging.error("Bad model output: %r", e)
        raise ApiError("The AI reply could not be read. Please try again.", 502)
    except requests.RequestException as e:
        logging.error("Network error: %r", e)
        raise ApiError("Could not reach the AI service.", 502)


def clean_tags(tags):
    out = []
    for t in tags if isinstance(tags, list) else []:
        t = "".join(str(t).split()).lstrip("#")
        if t:
            out.append("#" + t[:40])
    return out[:20]


def clean_posts(raw, platforms):
    posts = []
    for p in raw.get("posts", []):
        name = p.get("platform")
        content = str(p.get("content", "")).strip()[:3000]
        if name in platforms and content:
            posts.append({"platform": name, "content": content, "hashtags": clean_tags(p.get("hashtags"))})
    if not posts:
        raise ApiError("The AI returned no posts. Please try again.", 502)
    return posts


POSTS_SHAPE = ('{"posts":[{"platform":"<exact platform name>","content":"post text without hashtags",'
               '"hashtags":["#tag1","#tag2"]}]')


@app.get("/")
def home():
    return app.send_static_file("index.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", model=MODEL, key_loaded=bool(API_KEY))


@app.post("/api/generate")
def generate():
    d = request.get_json(silent=True) or {}
    topic, audience, tone = text(d, "topic", 1200), text(d, "audience", 200), text(d, "tone", 40) or "Professional"
    platforms = pick_platforms(d)
    if len(topic) < 3:
        raise ApiError("Please enter a topic or short brief.")
    system = (
        "You are an expert social media copywriter. Write one post per requested platform, "
        "following its style rules. Never put hashtags inside the content; list them separately.\n"
        f"Platform rules:\n{rules_for(platforms)}\n"
        f"Also give 4 short extra post ideas for this topic. Return ONLY valid JSON shaped like: "
        f'{{"posts":[...],"ideas":["idea"]}} where posts look like {POSTS_SHAPE[9:]}. '
        "Write in the language of the topic."
    )
    user = f"Topic: {topic}\nAudience: {audience or 'general audience'}\nTone: {tone}\nPlatforms: {', '.join(platforms)}"
    raw = ask(system, user)
    ideas = [str(i).strip()[:160] for i in raw.get("ideas", []) if str(i).strip()][:6]
    return jsonify(posts=clean_posts(raw, platforms), ideas=ideas)


@app.post("/api/repurpose")
def repurpose():
    d = request.get_json(silent=True) or {}
    original, audience, tone = text(d, "original", 3000), text(d, "audience", 200), text(d, "tone", 40) or "Professional"
    platforms = pick_platforms(d)
    if len(original) < 10:
        raise ApiError("Please paste the post you want to repurpose.")
    system = (
        "You are an expert social media editor. Rewrite the user's original post for each requested platform, "
        "keeping the same message but adapting length, structure and style. Never put hashtags inside the content.\n"
        f"Platform rules:\n{rules_for(platforms)}\n"
        f"Return ONLY valid JSON shaped like: {POSTS_SHAPE}. Write in the language of the original post."
    )
    user = f"Original post:\n{original}\n\nAudience: {audience or 'general audience'}\nTone: {tone}\nPlatforms: {', '.join(platforms)}"
    return jsonify(posts=clean_posts(ask(system, user), platforms))


@app.post("/api/calendar")
def calendar():
    d = request.get_json(silent=True) or {}
    topic, audience, tone = text(d, "topic", 1200), text(d, "audience", 200), text(d, "tone", 40) or "Professional"
    platforms = pick_platforms(d)
    if len(topic) < 3:
        raise ApiError("Please enter a topic or short brief.")
    system = (
        "You are a social media strategist. Build a 7-day content calendar (Monday to Sunday) that mixes "
        "content types (education, behind the scenes, social proof, promotion, engagement). Rotate through the "
        "requested platforms only. Return ONLY valid JSON shaped like: "
        '{"days":[{"day":"Monday","platform":"LinkedIn","format":"Text post","idea":"one-sentence post idea",'
        '"best_time":"9:00 AM"}]}. Exactly 7 entries. Write in the language of the topic.'
    )
    user = f"Topic: {topic}\nAudience: {audience or 'general audience'}\nTone: {tone}\nPlatforms: {', '.join(platforms)}"
    raw = ask(system, user, 1800)
    days = []
    for i, e in enumerate(raw.get("days", [])[:7]):
        idea = str(e.get("idea", "")).strip()[:240]
        if idea:
            plat = e.get("platform") if e.get("platform") in platforms else platforms[i % len(platforms)]
            days.append({"day": DAYS[i], "platform": plat, "format": str(e.get("format", "")).strip()[:40],
                         "idea": idea, "best_time": str(e.get("best_time", "")).strip()[:20]})
    if not days:
        raise ApiError("The AI returned no calendar. Please try again.", 502)
    return jsonify(days=days)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
