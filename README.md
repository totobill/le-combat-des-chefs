# Le Combat des Chefs

Application d'animation pour séminaire : épreuves, classement live, PWA.

**URL production :** https://combat-des-chefs.lafrenchsphere.fr

## Stack

- **Frontend** : Angular 19 + PWA
- **Backend** : FastAPI + WebSockets
- **BDD** : PostgreSQL + Alembic
- **Déploiement** : Docker Compose + GitHub Actions (runner self-hosted) + Cloudflare Tunnel

## Démarrage local

```bash
make dev    # PostgreSQL + API + Angular — http://localhost:4200
```

Une seule commande : Docker lance toute la stack. Les modifications dans `frontend/` et `backend/` sont détectées automatiquement (scan toutes les 2 s, sans surcharge navigateur).

```bash
make dev-down    # arrêter
make dev-logs    # suivre les logs
POLL_MS=3000 make dev   # intervalle de scan personnalisé (ms)
```

> Ne pas utiliser `make prod-up` pour le dev : image figée, pas de hot reload.

### Production Docker (iMac)

Port applicatif par défaut : **8091** (`PORT_APP_PROD` dans `.env.prod`).

```bash
cp .env.prod.example .env.prod   # puis éditer les secrets
make prod-deploy                 # migrate + build + up + health
make prod-logs
```

## Auth

- **Admin / animateur** : mot de passe `ADMIN_PASSWORD` (défaut `combat2026`) → `/admin/login`
- **Équipes** : `/join` → prénom + choix d'équipe (code session `CHEFS`)

## Écrans

| Route | Usage |
|-------|--------|
| `/` | Accueil |
| `/join` | Connexion équipe (téléphone) |
| `/team` | Jeu équipe |
| `/admin/login` | Connexion admin |
| `/admin` | Config équipes & barèmes |
| `/host` | Animateur — lancer épreuves |
| `/board` | Grand écran / TV |

## Production (iMac)

1. Runner GitHub : labels `self-hosted`, `combat-des-chefs`
2. Variable dépôt `PRODUCTION_ENV_FILE` → chemin absolu vers `.env.prod` (voir `.env.prod.example`)
3. Push sur `main` → workflow `Deploy production`

## Épreuves

- **MDP** — Mot de passe (30 s/joueur, téléphone au front)
- **DCC** — Duo / Carré / Cash (choix difficulté par équipe)
- **Chips** — Dégustation aveugle
- **Mölkky** — Saisie admin fin de match
- **Paroles** — Mots manquants (capitaine)
- **Piscine** — Relais, saisie admin
- **Poignards** — Finale, handicaps temps selon classement
