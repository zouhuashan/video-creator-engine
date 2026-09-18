# ArcReel local sidecar

This wrapper runs the official ArcReel image as an optional local-only service.
It binds port `1241` to `127.0.0.1`, stores ArcReel runtime data below `data/`,
and keeps credentials and provider settings outside Git.

```bash
cp integrations/arcreel/.env.example integrations/arcreel/.env
docker compose -f integrations/arcreel/compose.yml up -d
```

Open <http://127.0.0.1:1241>. The VideoCreator Web console connects through
the ArcReel workspace adapter. Remote generation providers remain optional and
must be configured in ArcReel separately.

Powered by ArcReel — https://github.com/ArcReel/ArcReel
