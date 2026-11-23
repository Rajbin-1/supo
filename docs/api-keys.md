# AssemblyAI and Gemini API Keys

SupoClip uses AssemblyAI to transcribe audio and a language model to select clips. This guide sets up AssemblyAI and Google's Gemini model.

## 1. Create an AssemblyAI key

1. Sign in or create an account at [AssemblyAI](https://www.assemblyai.com/).
2. Open the API keys section in your AssemblyAI account.
3. Create or copy an API key.

## 2. Create a Gemini key

1. Open [Google AI Studio](https://aistudio.google.com/app/apikey) and sign in.
2. Create an API key.
3. Copy the key. SupoClip reads Gemini credentials from `GOOGLE_API_KEY`.

## 3. Add the keys to SupoClip

From the project directory, create your local environment file:

```bash
cp .env.example .env
```

Open `.env` and set these values:

```env
ASSEMBLY_AI_API_KEY=your_assemblyai_api_key
LLM=google-gla:gemini-3-flash-preview
GOOGLE_API_KEY=your_google_ai_studio_api_key
```

Before starting, also replace the authentication and encryption placeholders in `.env` as explained in the [setup guide](setup.md).

Replace the example values with your own keys, without quotes. Then start or restart the app:

```bash
docker compose up -d --build
```

## Keep your keys private

- Do not commit `.env`, paste keys into source code, or share them in screenshots or logs.
- `.env` is ignored by Git. The shareable `.env.example` contains blank API-key values and placeholders for local secrets.
- If a key is exposed, revoke it in its provider account and create a replacement.
