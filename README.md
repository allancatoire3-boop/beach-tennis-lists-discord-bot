# Bot des listes chronologiques Beach Tennis

Ce troisième bot ne consulte pas Ten'Up. Il lit les fichiers JSON produits par les deux bots existants :

- liste Montpellier sur trois mois ;
- liste France métropolitaine et Corse sur douze mois.

Il s'exécute chaque jour à 06:02 UTC, après les deux bots de détection. Lorsqu'il constate au moins un nouvel identifiant de tournoi, il publie une nouvelle liste chronologique dans le salon concerné.

Les tournois dont la date de fin est antérieure à la date du jour sont exclus. Un tournoi en cours reste affiché jusqu'à sa date de fin incluse.

## Secrets nécessaires

Dans **Settings → Secrets and variables → Actions** :

- `DISCORD_WEBHOOK_MONTPELLIER_URL`
- `DISCORD_WEBHOOK_FRANCE_URL`

## Premier démarrage

Avant le premier lancement de ce bot, exécuter une fois les workflows des bots Montpellier et France afin qu'ils produisent leurs fichiers de résultats.

Ensuite, dans **Actions**, ouvrir **Publier les listes chronologiques** puis **Run workflow**.

Le premier lancement initialise silencieusement la mémoire. Les listes ne sont publiées que lorsqu'un nouveau tournoi est ajouté par la suite.
