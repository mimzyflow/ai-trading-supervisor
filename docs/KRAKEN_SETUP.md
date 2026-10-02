# Kraken - intervention manuelle

Cette étape reste volontairement hors automatisation car elle touche à l'identité et aux secrets du compte.

## Compte
1. Ouvrir ou finaliser le compte Kraken.
2. Terminer la vérification d'identité demandée par Kraken.
3. Activer la 2FA du compte.
4. Ne déposer aucun capital tant que le dry-run n'est pas validé.

## Clé API du bot
Créer une clé API dédiée, distincte de toute autre intégration.

Permissions prévues pour le trading réel :
- consultation des ordres et transactions ;
- modification / passage d'ordres ;
- annulation / fermeture d'ordres ;
- éventuellement consultation du solde si nécessaire au bot.

Ne jamais autoriser :
- retrait de fonds ;
- modification des paramètres de sécurité ;
- toute permission inutile au fonctionnement du bot.

## Secrets
Les valeurs seront stockées uniquement sur Oracle dans un fichier `.env` ignoré par Git :
```
KRAKEN_API_KEY=...
KRAKEN_API_SECRET=...
GITHUB_STATUS_TOKEN=...
```

Le jeton GitHub doit être limité au dépôt `ai-trading-supervisor` et à la mise à jour du ticket de statut.
