-- =====================================================================================
-- Dictum – Grundschema
--
-- Eine "Migration" ist eine Datei mit SQL-Befehlen, die die Datenbank Schritt für
-- Schritt aufbaut. Sie liegt im Repo, damit jede Änderung an der Datenbank genauso
-- nachvollziehbar ist wie Änderungen am Code. Der Zeitstempel im Dateinamen legt
-- die Reihenfolge fest.
-- =====================================================================================


-- -------------------------------------------------------------------------------------
-- 1. Aufzählungstypen: nur diese Werte sind erlaubt
-- -------------------------------------------------------------------------------------

-- Diktat (kurz, wird bereinigt) oder Gespräch (lang, wird zusammengefasst)
create type public.recording_kind as enum ('dictation', 'conversation');

-- Der Lebenszyklus einer Aufnahme:
--   uploading → transcribing → summarizing → done
--                    └──────────────┴────────→ error
create type public.recording_status as enum ('uploading', 'transcribing', 'summarizing', 'done', 'error');


-- -------------------------------------------------------------------------------------
-- 2. Tabellen
-- -------------------------------------------------------------------------------------

create table public.recordings (
  id               uuid primary key default gen_random_uuid(),
  -- auth.uid() = ID des eingeloggten Nutzers. Als Standardwert muss der Client
  -- die user_id nicht selbst mitschicken (und kann sie so auch nicht fälschen,
  -- siehe Policies unten).
  user_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind             public.recording_kind not null default 'conversation',
  template         text not null default 'meeting'
                   check (template in ('meeting', 'interview', 'lecture', 'note')),
  source           text not null default 'pwa' check (source in ('pwa', 'desktop')),
  status           public.recording_status not null default 'uploading',
  title            text,
  language         text not null default 'de',
  duration_seconds numeric,
  -- Wie viele Audio-Stücke insgesamt kommen. Erst wenn das bekannt ist UND alle
  -- Stücke transkribiert sind, startet die Zusammenfassung.
  chunk_count      int check (chunk_count > 0),
  transcript       text,
  -- Ergebnis der KI als JSON (Kurzfassung, Kernpunkte, To-dos …) bzw. bei Diktaten
  -- der bereinigte Text. JSON, weil sich die Struktur je nach Vorlage unterscheidet.
  summary          jsonb,
  error            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  -- Volltextsuche auf Deutsch ("Besprechungen" findet auch "Besprechung").
  -- "generated … stored" = Postgres berechnet die Spalte automatisch bei jeder Änderung.
  search           tsvector generated always as (
                     to_tsvector('german', coalesce(title, '') || ' ' || coalesce(transcript, ''))
                   ) stored
);

comment on table public.recordings is 'Eine Aufnahme (Diktat oder Gespräch) mit Transkript und KI-Ergebnis.';

create index recordings_user_created_idx on public.recordings (user_id, created_at desc);
create index recordings_search_idx on public.recordings using gin (search);


-- Lange Aufnahmen werden in ~5-Minuten-Stücke geteilt (Grenzen: 25 MB bei OpenAI,
-- 150 s Laufzeit pro Edge Function). Jedes Stück wird einzeln transkribiert.
create table public.recording_chunks (
  recording_id     uuid not null references public.recordings (id) on delete cascade,
  idx              int not null check (idx >= 0),
  user_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  storage_path     text not null,
  duration_seconds numeric,
  status           text not null default 'pending' check (status in ('pending', 'done', 'error')),
  transcript       text,
  error            text,
  created_at       timestamptz not null default now(),
  primary key (recording_id, idx)
);

create index recording_chunks_user_idx on public.recording_chunks (user_id);


-- Persönliches Wörterbuch und Snippets – dieselbe Idee wie dictionary.txt und
-- snippets.toml am PC, aber in der Cloud, damit das Handy sie auch nutzen kann.
create table public.dictionary_terms (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  term       text not null check (length(term) between 1 and 100),
  created_at timestamptz not null default now(),
  unique (user_id, term)
);

create table public.snippets (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  trigger    text not null check (length(trigger) between 1 and 100),
  text       text not null,
  created_at timestamptz not null default now(),
  unique (user_id, trigger)
);


-- -------------------------------------------------------------------------------------
-- 3. updated_at automatisch pflegen
-- -------------------------------------------------------------------------------------

create function public.set_updated_at()
returns trigger
language plpgsql
-- Leerer search_path: Funktionen sollen nur voll qualifizierte Namen benutzen,
-- damit niemand über ein gleichnamiges Objekt in einem anderen Schema eingreifen kann.
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger recordings_set_updated_at
  before update on public.recordings
  for each row execute function public.set_updated_at();


-- -------------------------------------------------------------------------------------
-- 4. Row Level Security (RLS)
--
-- Ohne RLS könnte jeder mit dem öffentlichen API-Schlüssel ALLE Zeilen lesen.
-- Mit RLS prüft die Datenbank bei jeder Abfrage: Gehört diese Zeile dem
-- eingeloggten Nutzer? Wenn nicht, ist sie unsichtbar – egal was der Client schickt.
--
-- "(select auth.uid())" statt "auth.uid()": so rechnet Postgres den Wert einmal pro
-- Abfrage aus statt einmal pro Zeile (Empfehlung von Supabase für Performance).
-- -------------------------------------------------------------------------------------

alter table public.recordings       enable row level security;
alter table public.recording_chunks enable row level security;
alter table public.dictionary_terms enable row level security;
alter table public.snippets         enable row level security;

create policy "Eigene Aufnahmen" on public.recordings
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Eigene Audio-Stücke" on public.recording_chunks
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check (
    (select auth.uid()) = user_id
    -- Ein Stück darf nur an eine EIGENE Aufnahme gehängt werden
    and exists (
      select 1 from public.recordings r
      where r.id = recording_id and r.user_id = (select auth.uid())
    )
  );

create policy "Eigenes Wörterbuch" on public.dictionary_terms
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Eigene Snippets" on public.snippets
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);


-- -------------------------------------------------------------------------------------
-- 5. Zusammenfassung starten – genau einmal
--
-- Mehrere Audio-Stücke werden parallel transkribiert. Wer startet danach die
-- Zusammenfassung? Ohne Absprache könnten zwei gleichzeitig fertig werdende Stücke
-- sie doppelt starten (doppelte Kosten). Diese Funktion löst das in der Datenbank:
-- Das UPDATE mit "where status = 'transcribing'" kann nur EIN Aufrufer gewinnen,
-- weil Postgres die Zeile dabei sperrt. Alle anderen bekommen false zurück.
--
-- "security invoker" = läuft mit den Rechten des Aufrufers, RLS gilt also weiter.
-- -------------------------------------------------------------------------------------

create function public.try_start_summary(p_recording_id uuid, p_force boolean default false)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_done  int;
  v_total int;
begin
  select count(*) filter (where c.status = 'done'), r.chunk_count
    into v_done, v_total
    from public.recordings r
    left join public.recording_chunks c on c.recording_id = r.id
   where r.id = p_recording_id
   group by r.chunk_count;

  -- Noch nicht alle Stücke da bzw. transkribiert → später nochmal
  if v_total is null or v_done < v_total then
    return false;
  end if;

  update public.recordings r
     set status = 'summarizing',
         error = null,
         -- Teil-Transkripte in der richtigen Reihenfolge zusammensetzen
         transcript = (
           select string_agg(c.transcript, E'\n\n' order by c.idx)
             from public.recording_chunks c
            where c.recording_id = r.id
         )
   where r.id = p_recording_id
     and (
       r.status = 'transcribing'
       -- force: erneut zusammenfassen (z. B. mit anderer Vorlage) oder nach Fehler
       or (p_force and r.status in ('done', 'error'))
     );

  return found;
end;
$$;

-- Nur eingeloggte Nutzer dürfen die Funktion aufrufen
revoke execute on function public.try_start_summary(uuid, boolean) from public, anon;
grant execute on function public.try_start_summary(uuid, boolean) to authenticated;

comment on function public.try_start_summary is
  'Setzt eine Aufnahme atomar auf summarizing, sobald alle Stücke transkribiert sind. true = Aufrufer soll zusammenfassen.';


-- -------------------------------------------------------------------------------------
-- 6. Storage: privater Bucket für Audio
--
-- Pfad-Schema: {user_id}/{recording_id}/{idx}.webm
-- Der erste Ordner ist die Nutzer-ID – die Policies erlauben nur Zugriff auf den
-- eigenen Ordner.
-- -------------------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'recordings', 'recordings', false,
  26214400,  -- 25 MB, das Limit der OpenAI-Transkription
  array['audio/webm', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/mp4', 'audio/mpeg', 'audio/m4a']
);

create policy "Eigenes Audio lesen" on storage.objects
  for select to authenticated
  using (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "Eigenes Audio hochladen" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "Eigenes Audio ersetzen" on storage.objects
  for update to authenticated
  using (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);

create policy "Eigenes Audio löschen" on storage.objects
  for delete to authenticated
  using (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);
