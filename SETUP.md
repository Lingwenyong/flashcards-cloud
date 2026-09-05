# One-time cloud setup

This version is designed so the same flashcard decks appear on your Mac, iPhone and iPad.

You only need to do this setup once.

## 1. Create a free Supabase project

Go to Supabase and create a new project.

Inside the project:

1. Open **SQL Editor**
2. Create a new query
3. Copy everything from `supabase_schema.sql`
4. Run it

This creates the private `decks` table and security rules. Every account can only read, edit, and delete its own decks.

## 2. Get the Supabase connection values

In the Supabase project settings/API section, copy:

- Project URL
- anon/public key

You will use these as:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

## 3. Put the project on GitHub

Create a private GitHub repository and upload the files in this folder.

Do **not** upload a real `.streamlit/secrets.toml` containing your keys.

## 4. Deploy with Streamlit Community Cloud

Create a Streamlit Community Cloud app using the GitHub repository.

Main file:

`app.py`

In the Streamlit app's **Secrets** settings, paste:

```toml
OPENAI_API_KEY = "your-openai-api-key"
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_ANON_KEY = "your-supabase-anon-key"
```

Deploy/reboot the app.

## 5. Open it on every device

Streamlit will give you one HTTPS web address.

Open that same address on:

- Mac
- iPhone
- iPad

Create your account/sign in with the same email and password on every device.

Your generated decks are then stored in Supabase, not on one device.

## iPhone / iPad home-screen icon

In Safari:

1. Open your flashcard website
2. Tap **Share**
3. Tap **Add to Home Screen**

Then it behaves much more like a normal app.

## PDFs

Uploaded PDFs are processed only for generation. This app does not save the PDFs in Supabase.

Only the generated flashcard deck is saved.
