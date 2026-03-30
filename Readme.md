Face attendance app with static HTML screens and a Flask backend.

Setup:

1. Create a Supabase project.
2. Run [`supabase_schema.sql`](/c:/Users/ayush/Desktop/chander sir/face-attendence/supabase_schema.sql) in the Supabase SQL editor.
3. Copy [`.env.example`](/c:/Users/ayush/Desktop/chander sir/face-attendence/.env.example) to `.env` and fill in your Supabase values.
4. Install dependencies with `pip install -r requirements.txt`.
5. Run `python server.py`.
6. Run `python main.py` if you want the desktop webview.

Flow:

- Browser app runs at `http://localhost:5050` by default.
- Student registers once with email, roll number, password, profile image, and 5 face images.
- Images are stored in the Supabase storage bucket.
- Student logs in with roll number and password.
- Attendance is marked only after live camera capture matches the registered face images.
