# AI Social Media Automation Tool

Flask (Python 3.11.9) + OpenRouter backend, HTML/CSS/JS frontend. Flask serves the page, so Live Server is not needed.

## Run (Windows, VS Code terminal)
1. Open this folder in VS Code (File > Open Folder).
2. Get a key at https://openrouter.ai/keys
3. In the terminal (Ctrl + `):
   ```
   py -3.11 -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```
4. Open `.env` and paste your key after `OPENROUTER_API_KEY=`
5. Start: `python app.py`
6. Open http://127.0.0.1:5000

Check http://127.0.0.1:5000/api/health shows `"key_loaded": true`.
Change the AI model with `OPENROUTER_MODEL` in `.env`.
