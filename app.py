"""
AI Social Media Automation Tool
Flask + OpenRouter API | Python 3.11 | Render deployment
"""
import json
import logging
import os

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SITE_URL = os.getenv("SITE_URL", "http://localhost:5000").strip()
SITE_NAME = os.getenv("SITE_NAME", "AI Social Media Automation Tool").strip()
PORT = int(os.getenv("PORT", "5000"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

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
        self.message = message
        self.status = status


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify(error=error.message), error.status


@app.errorhandler(413)
def handle_request_too_large(_error):
    return jsonify(error="Request is too large."), 413


def get_json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Please send a valid JSON request.")
    return data


def text(data, key, limit):
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        raise ApiError(f"Invalid value for '{key}'.")
    return str(value).strip()[:limit]


def pick_platforms(data):
    raw = data.get("platforms", [])
    if not isinstance(raw, list):
        raise ApiError("Platforms must be provided as a list.")
    chosen = []
    for platform in raw:
        if isinstance(platform, str) and platform in PLATFORM_RULES and platform not in chosen:
            chosen.append(platform)
    if not chosen:
        raise ApiError("Choose at least one valid platform.")
    return chosen


def rules_for(platforms):
    return "\n".join(f"- {p}: {PLATFORM_RULES[p]}" for p in platforms)


def extract_json(content):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Empty model response.")
    content = content.strip()
    try:
        result = json.loads(content)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object in model response.")
    result = json.loads(content[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("Model JSON must be an object.")
    return result


def ask(system, user, max_tokens=2200):
    if not API_KEY:
        app.logger.error("OPENROUTER_API_KEY is not configured.")
        raise ApiError("Server is missing its OpenRouter API key. Configure it in Render Environment Variables.", 500)

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": SITE_URL,
        "X-Title": SITE_NAME,
    }

    try:
        response = requests.post(
            OPENROUTER_URL, headers=headers, json=payload, timeout=(10, 60)
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return extract_json(content)
    except requests.Timeout:
        raise ApiError("The AI took too long. Please try again.", 504)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        detail = error.response.text[:500] if error.response is not None else ""
        app.logger.error("OpenRouter HTTP %s: %s", status, detail)
        raise ApiError("The AI service returned an error. Check your API key, account credits, and model.", 502)
    except requests.RequestException:
        app.logger.exception("Network error contacting OpenRouter.")
        raise ApiError("Could not reach the AI service. Please try again.", 502)
    except (ValueError, KeyError, IndexError, AttributeError, TypeError):
        app.logger.exception("Could not parse OpenRouter response.")
        raise ApiError("The AI reply could not be read. Please try again.", 502)


def clean_tags(tags):
    output = []
    for tag in tags if isinstance(tags, list) else []:
        tag = "".join(str(tag).split()).lstrip("#")
        if tag:
            output.append("#" + tag[:40])
    return output[:20]


def clean_posts(raw, platforms):
    if not isinstance(raw, dict) or not isinstance(raw.get("posts", []), list):
        raise ApiError("The AI returned invalid post data. Please try again.", 502)
    posts = []
    for post in raw.get("posts", []):
        if not isinstance(post, dict):
            continue
        platform = post.get("platform")
        content = str(post.get("content", "")).strip()[:3000]
        if platform in platforms and content:
            posts.append({
                "platform": platform,
                "content": content,
                "hashtags": clean_tags(post.get("hashtags")),
            })
    if not posts:
        raise ApiError("The AI returned no posts. Please try again.", 502)
    return posts


POSTS_SHAPE = (
    '{"posts":[{"platform":"<exact platform name>","content":"post text without hashtags",'
    '"hashtags":["#tag1","#tag2"]}]}'
)


@app.get("/")
def home():
    return app.send_static_file("index.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", model=MODEL, key_loaded=bool(API_KEY)), 200


@app.post("/api/generate")
def generate():
    data = get_json_body()
    topic = text(data, "topic", 1200)
    audience = text(data, "audience", 200)
    tone = text(data, "tone", 40) or "Professional"
    platforms = pick_platforms(data)
    if len(topic) < 3:
        raise ApiError("Please enter a topic or short brief.")

    system = (
        "You are an expert social media copywriter. Write one post per requested platform, "
        "following its style rules. Never put hashtags inside the content; list them separately.\n"
        f"Platform rules:\n{rules_for(platforms)}\n"
        "Also give 4 short extra post ideas for this topic. Return ONLY valid JSON shaped like: "
        f'{{"posts":[...],"ideas":["idea"]}} where posts look like {POSTS_SHAPE[9:]}. '
        "Write in the language of the topic."
    )
    user = f"Topic: {topic}\nAudience: {audience or 'general audience'}\nTone: {tone}\nPlatforms: {', '.join(platforms)}"
    raw = ask(system, user)
    raw_ideas = raw.get("ideas", [])
    ideas = [str(i).strip()[:160] for i in raw_ideas if str(i).strip()][:6] if isinstance(raw_ideas, list) else []
    return jsonify(posts=clean_posts(raw, platforms), ideas=ideas)


@app.post("/api/repurpose")
def repurpose():
    data = get_json_body()
    original = text(data, "original", 3000)
    audience = text(data, "audience", 200)
    tone = text(data, "tone", 40) or "Professional"
    platforms = pick_platforms(data)
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
    data = get_json_body()
    topic = text(data, "topic", 1200)
    audience = text(data, "audience", 200)
    tone = text(data, "tone", 40) or "Professional"
    platforms = pick_platforms(data)
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
    raw_days = raw.get("days", [])
    if not isinstance(raw_days, list):
        raise ApiError("The AI returned invalid calendar data. Please try again.", 502)

    days = []
    for entry in raw_days[:7]:
        if not isinstance(entry, dict):
            continue
        idea = str(entry.get("idea", "")).strip()[:240]
        if not idea:
            continue
        platform = entry.get("platform")
        if platform not in platforms:
            platform = platforms[len(days) % len(platforms)]
        days.append({
            "day": DAYS[len(days)],
            "platform": platform,
            "format": str(entry.get("format", "")).strip()[:40],
            "idea": idea,
            "best_time": str(entry.get("best_time", "")).strip()[:20],
        })
    if not days:
        raise ApiError("The AI returned no calendar. Please try again.", 502)
    return jsonify(days=days)


if __name__ == "__main__":
    # Render uses Gunicorn; this is only for local development.
    app.run(host="0.0.0.0", port=PORT, debug=False)
