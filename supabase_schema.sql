create extension if not exists "pgcrypto";

create table if not exists public.students (
  id uuid primary key,
  user_id uuid unique not null,
  roll_no text unique not null,
  first_name text not null,
  last_name text,
  full_name text not null,
  email text unique not null,
  phone text,
  dob date,
  gender text,
  department text,
  year text,
  emergency_name text,
  emergency_phone text,
  address text,
  profile_image_path text,
  face_images_count integer not null default 5,
  registered_at timestamptz not null default timezone('asia/kolkata', now())
);

create table if not exists public.attendance_records (
  id uuid primary key default gen_random_uuid(),
  student_id uuid references public.students(id) on delete cascade,
  roll_no text not null,
  full_name text not null,
  department text,
  year text,
  attendance_date date not null,
  attendance_time time not null,
  status text not null default 'present',
  confidence numeric(5,2),
  created_at timestamptz not null default timezone('asia/kolkata', now()),
  unique (roll_no, attendance_date)
);

create index if not exists idx_students_roll_no on public.students(roll_no);
create index if not exists idx_students_email on public.students(email);
create index if not exists idx_attendance_date on public.attendance_records(attendance_date);
create index if not exists idx_attendance_roll on public.attendance_records(roll_no);

insert into storage.buckets (id, name, public)
values ('student-faces', 'student-faces', false)
on conflict (id) do nothing;
