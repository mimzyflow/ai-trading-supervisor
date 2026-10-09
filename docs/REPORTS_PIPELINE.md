# Rapports crypto et actions dans Jarvis

La [salle des marchés supervisée](MARKET_ROOM.md) ajoute quatre desks de
lecture et un connecteur TradingAgents isolé. Les avis externes restent
consultatifs. Un arrêt de risque enregistré est préservé lors d'un déploiement.

Les deux portefeuilles sont des simulations privées sur Oracle. Le moteur
crypto Freqtrade conserve son historique et son contrôle V2 ; les actions
utilisent un portefeuille brokerless en USD et trois shadows séparés.

## Emplacement et cadence

- Code actif : `/home/ubuntu/ai-trading-supervisor`, version dans `build-info.json`.
- Rapport regroupé : `user_data/reports/latest.json` et `latest.md`.
- Recherche et états papier : `user_data/reports/autonomy.json`.
- Copie lue par Jarvis : `/var/lib/jarvis/runtime/trading/latest.json`.
- Rapport moteur toutes les cinq minutes ; archive Markdown horaire dans les
  rapports privés. Le timer `trading-research.timer` contrôle le risque toutes
  les cinq minutes, et calcule la recherche quotidienne.
- Jarvis : panneau **Trading IA**, commandes `/trading` ou `/rapports-trading`,
  téléchargement privé `/api/trading/report`. Le connecteur Moussa Commander
  `trading_status` lit le même état via l'endpoint interne loopback uniquement.

La lecture est indépendante de l'ouverture du Mac. Aucun nouveau service
payant, token ou accès public n'est nécessaire. La publication automatique dans
le ticket GitHub demeure optionnelle et non configurée faute de jeton dédié.
Cette absence ne signifie plus que le moteur local est en panne. Les erreurs
d'une publication configurée restent visibles.

## Ce qui manquait

La copie vers Jarvis fonctionnait, mais le producteur ne transmettait pas les
valeurs du portefeuille actions ni les motifs de rejet V3. Le lecteur et le
panneau Jarvis ignoraient également ces sections. Le rapport transmet maintenant
les comptes, devises, dernières séances, versions d'exécution, blocages et
résultats historiques bornés. Aucun brut de marché ni identifiant n'est exposé.

Les dates de collecte et les dates de marché sont distinctes. Une collecte
ancienne/future/invalide supprime les chiffres utilisables. Une panne Yahoo
conserve l'ancien bundle comme preuve, refuse les nouvelles décisions actions
et laisse fonctionner le contrôle crypto. Les opérations sur titres nouvelles
requièrent une revue avant de produire des transactions ou du P/L.

### Bougie récente incohérente chez Yahoo

Le 9 octobre après clôture, le flux `range=2y` de Unity (U) fournit une
ouverture de 46,1599998474 USD sous son plus bas de 46,2599983215 USD.
Le flux quotidien court présente aussi cette anomalie par intermittence.
Le collecteur peut récupérer les extrêmes incohérents parmi les cinq dernières
séances, datées de sept jours au plus, à partir du flux `range=5d&interval=5m`.
Les 78 barres consécutives de la séance régulière doivent toutes être présentes,
avec OHLC et volume valides. Ouverture, clôture et extrême quotidien déjà
cohérent doivent correspondre au flux intraday. Les volumes intraday ne peuvent
pas dépasser le volume quotidien publié ; ce dernier est conservé tel quel.
Seul le high/low incohérent est remplacé par le maximum/minimum réellement
observé dans ces barres. Aucun prix n'est inventé, aucun intervalle manquant
n'est interpolé et aucune séance n'est supprimée.

Deux requêtes supplémentaires au plus par collecte, sans retry, avec les
mêmes limites HTTP et refus des redirections. Les empreintes du flux initial
et du flux de récupération, leur URL, la date et les séances remplacées sont
conservées dans la provenance du bundle ; `equity_collection.json` énumère
les récupérations. L'historique des opérations sur titres demeure celui du
flux primaire `events=div,splits` ; il n'est ni supprimé ni remplacé.
Identité, devise, OHLCV, clôture et opérations sur titres
doivent rester cohérents. Une récupération absente/invalide, une anomalie
ancienne ou un budget épuisé conserve l'ancien bundle et bloque les décisions
actions. Les motifs d'erreur connus sont exposés sous forme de codes fermés,
sans publier le message brut de la source. Yahoo reste l'unique fournisseur :
cette récupération ne constitue pas un recoupement indépendant.

## Méthodes et efficacité

La crypto cumulée inclut l'ancienne baseline ; les clôtures V2 sont affichées
séparément après le 5 octobre 15:03 UTC. EUR et USD ne sont jamais additionnés.
Zéro transaction actions signifie absence de preuve, et non stratégie validée.

Les challengers quotidiens Python ne reproduisent pas les classes Freqtrade
natives 1h/4h. Le papier actions reste un modèle quotidien avec entrées et
sorties de tendance/temps à la clôture, stops et gaps conservateurs ; ce n'est
pas une preuve de prix exécutables chez un courtier. Les données Yahoo restent
une source unique, sans recoupement de prix ou de calendrier boursier.

Les corrections de causalité et de risque sont détaillées dans
[l'audit](TRADING_AUDIT_2026-10-08.md). Un changement de moteur ne rend pas les
anciens plans compatibles : une [révision explicite](RESEARCH_RESUME.md) conserve
les preuves et fixe un nouveau gel prospectif. Les anciens résultats V3 sont
archivés par empreinte avant recalcul. Leur cache doit correspondre au code,
aux actifs dans leur ordre d'exécution et à toutes les données simulées ;
une simple date de collecte rafraîchie ne modifie pas cette empreinte. Un
changement des données invalide les chiffres précédents jusqu'au succès du
recalcul. Aucun ordre réel n'est activé.

## Supervision configurée

Une revue Codex horaire, en lecture seule, est attachée à la
conversation (`surveillance-bots-crypto-et-actions`). Elle utilise le
connecteur `trading_status`, compare la fraîcheur et les changements, et
présente les points nécessitant une décision humaine. Les contrôles du
9 octobre à 19:49 et 20:49 UTC ont été exécutés ; la revue dépend toujours
de la disponibilité du poste Codex.
La collecte, les rapports et le contrôle de risque sur Oracle poursuivent
leur cadence propre toutes les cinq minutes, même sans ouverture du Mac.
