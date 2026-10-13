# supabase/

Backend in der Cloud (Projekt `dictum`, Region Frankfurt). Erklärung: [docs/backend.md](../docs/backend.md).

```
supabase/
├── config.toml      Einstellungen (Auth, Storage, Functions)
├── migrations/      Datenbank-Schema als SQL, in zeitlicher Reihenfolge
└── functions/       Edge Functions (TypeScript/Deno)
    ├── _shared/     Gemeinsamer Code: KI-Anbieter, Prompts, Vorlagen
    ├── transcribe/  Audio-Stück → Text (OpenAI)
    ├── summarize/   Transkript → Zusammenfassung (Claude)
    └── dictate/     Diktat vom Handy → bereinigter Text
```
