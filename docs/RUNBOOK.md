# Exploitation et accès Oracle

## Accès depuis le Mac

La méthode commune à Jarvis est reprise dans `scripts/oracle-ssh-target.sh` :
SSH Tailscale `ubuntu@100.88.175.94`, puis accès direct existant
`ubuntu@141.253.98.135`, clé privée locale `~/.ssh/jarvis-oracle.key`.
La clé n'est jamais copiée ni versionnée. Vérification stricte de la clé hôte,
BatchMode, timeout et refus explicite si les deux chemins sont indisponibles.

```sh
HOST=$(sh scripts/oracle-ssh-target.sh)
ssh -i "$HOME/.ssh/jarvis-oracle.key" -o BatchMode=yes -o StrictHostKeyChecking=yes "$HOST"
```

Projet Oracle : `/home/ubuntu/ai-trading-supervisor`.
Rapport assaini Jarvis : `/var/lib/jarvis/runtime/trading/latest.json`.
Ce dernier est lisible par le service Jarvis ; le compte SSH utilise uniquement
la voie administrateur déjà autorisée pour le diagnostic/déploiement.

## Configuration

- Kraken spot EUR, 100 EUR simulés, 2 positions de 20 EUR maximum.
- Dry-run forcé dans Compose et vérifié dans l'API du moteur.
- Aucune clé exchange dans le moteur de simulation ; la clé historique privée
  éventuelle reste hors Git et n'est plus injectée dans Freqtrade.
- Frais explicites nouveaux trades : 0,008 par côté. Historique ancien conservé.
- Freqtrade et Python Docker épinglés aux digests observés sur Oracle.
- API Freqtrade liée au localhost de l'hôte ; supervision interne par GET
  allowlistés, authentifiés, sans redirection ni méthode d'ordre/configuration.
- Aucun envoi d'ordre réel, levier, import n8n ou activation réelle depuis l'UI.

## Contrôles

`python3 scripts/check_simulation.py` refuse mode réel, périmètre différent,
clés exchange, overrides non revus et mises hors limites. Tests de supervision
pour API indisponible, base absente/corrompue, données invalides, mode réel,
rapports périmés et erreurs de publication.

Les healthchecks contrôlent la télémétrie moteur et le rapport local ; une
publication GitHub non configurée est une alerte distincte et ne signifie pas
que le moteur est arrêté. Valeur du portefeuille, P/L réalisé/latent/total,
capital engagé et baisse maximale observée sont exposés. Le risque au stop est
une estimation hors frais et glissement, jamais une perte maximale garantie.

## Publication GitHub

Sans `GITHUB_STATUS_TOKEN`, état `not_configured`, pas de faux succès.
Si souhaitée depuis Oracle, utiliser un jeton dédié avec accès au seul dépôt,
Issues lecture/écriture et metadata lecture, conservé dans `.env` privé.
Ne pas recopier un jeton global de compte. Les erreurs HTTP et timeouts sont
persistés sans texte susceptible d'exposer un secret et repris avec backoff.
Un rapport horaire GitHub est une observation datée, pas une preuve en direct.

## Déploiement / reprise

1. Vérifier Git et préserver tout travail concurrent ; travailler en branche.
2. Tests, compilation Python, `git diff --check`, validation de configuration.
3. Commit puis fast-forward/push normal, sans force-push.
4. `sh scripts/deploy-oracle.sh` : archive Git uniquement, hash vérifié, staging
   testé, copie de rollback, données et secrets préservés, contrôles de santé.
   Le Compose résolu est vérifié en capture privée avant toute copie active et
   avant chaque activation/restauration : DRY-RUN obligatoire, clés exchange
   absentes ou vides. Un refus initial laisse la version active intacte.
5. Vérifier `build-info.json`, les deux healthchecks, le mode dry-run effectif,
   l'absence de clés exchange injectées et le rapport vu par Jarvis.

La sauvegarde code est annoncée par le déploiement sous
`/home/ubuntu/trading-releases/previous-<date>`. Si l'activation échoue, le code
précédent est restauré. Le volume `ai-trading-freqtrade-runtime` est conservé.
La production Jarvis suit son mécanisme signé existant, jamais une copie libre
de code. Ne jamais réinitialiser la base pour embellir les résultats.

Toute future expérimentation est régie par `docs/RESEARCH_PROTOCOL.md`.
La reprise explicite après changement de code est décrite dans
[`RESEARCH_RESUME.md`](RESEARCH_RESUME.md). Elle conserve les preuves et réserve
126 séances strictement postérieures au nouveau gel.
Le passage en réel nécessite une conception et une validation humaine séparées.
