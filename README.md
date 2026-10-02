# AI Trading Supervisor

Projet personnel de trading automatisé en **simulation d'abord**.

## Architecture
- Freqtrade officiel, image Docker stable.
- Kraken spot, paires de test BTC/EUR et ETH/EUR.
- Capital simulé initial: 100 EUR.
- Stratégie de base: `MoussaBaseline`.
- Rapport technique et performance généré toutes les heures.
- Aucun secret Kraken n'est stocké dans Git.

## Règles de sécurité
- `dry_run=true` tant que Moussa n'a pas validé le passage réel.
- Aucun levier, futures ou marge dans la V1.
- Les futures clés Kraken ne doivent jamais autoriser les retraits.
- Les performances simulées ne garantissent pas les performances réelles.
- Une stratégie n'est jamais promue automatiquement en réel.

## Démarrage cible sur Oracle
```bash
docker compose pull
docker compose up -d
docker compose logs -f freqtrade
```

Voir `docs/RUNBOOK.md` pour les étapes de mise en service.
