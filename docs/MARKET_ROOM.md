# Salle des marchés supervisée

TradingAgents est une couche d'analyse consultative séparée des deux moteurs.
Son code et ses dépendances sont épinglés, dans un environnement Python dédié.
Source : https://github.com/TauricResearch/TradingAgents, version 0.6.0,
commit `1394a3f72aa4393e1a98f51b382434c4b4c2d972`, licence Apache-2.0.
Le nombre d'étoiles et les démonstrations du projet ne valident pas une rentabilité.

## Desks et rapports

- Crypto : état Kraken EUR observé, historique cumulé et V2 distingués.
- Actions : témoin et trois V3 brokerless USD, sans somme des comptes fictifs.
- Recherche : résultats historiques et refus V3, jamais assimilés au paper futur.
- Risque : garde déterministe existant, prioritaire sur tout avis IA.
- TradingAgents : analystes marché et actualités, débat haussier/baissier,
  contradicteurs de risque et avis final à examiner. Aucun raccordement courtier.

La salle déterministe est actualisée avec le rapport toutes les cinq minutes.
`user_data/reports/market-room.md` et `latest.json` en sont les sources Oracle.
Les avis détaillés résident dans `tradingagents.json` et `tradingagents.md`.
Les rapports précédents sont archivés avant remplacement. Jarvis reçoit une
copie privée fixe `room-analysis.json`, distincte de la télémétrie générale.
Jarvis : **Plus → Trading IA → Lire le rapport de la salle des marchés**.
Route privée authentifiée : `/api/trading/room-report`, texte non interprété,
sans paramètres de chemin. Commander `trading_status` expose les états et avis
bornés ; les textes des modèles ne deviennent jamais des instructions d'outil.

## Coût et limites

L'intégration utilise le pont de raisonnement Jarvis existant, loopback
`127.0.0.1:20129`, déjà employé par Hermes. Les clés fournisseurs, routage,
cooldowns et plafonds de consommation restent dans Jarvis. Le connecteur
n'obtient que le jeton de ce pont, privé dans `.runtime/`. Il ne peut exécuter
aucun outil. Aucun fournisseur ou secours payant supplémentaire n'est activé.
Le budget de cette intégration est fixé à 0 EUR ; cela n'est pas un audit de
la facture du compte fournisseur existant. Le modèle final derrière le relais
n'est pas attesté par ce pilote (`actual_upstream_model_verified=false`).

**Adaptation au projet, pas lancement de la CLI de trading amont** : les agents
haussier, baissier, directeur de recherche, trader consultatif, trois
contradicteurs de risque et gérant de TradingAgents travaillent sur les
rapports vérifiés des deux desks, **CRYPTO-EUR et ACTIONS-USD**. Les métriques
indisponibles restent nulles et les checkpoints sont datés. Aucun flux
indépendant de nouvelles, fondamentaux ou sentiment n'est ajouté ; les agents
reçoivent explicitement ces absences. Aucun compte vide n'est inventé.

Une tentative quotidienne à 20:20 UTC après clôture US, deux analyses au plus,
16 appels maximum par desk, 240 000 caractères cumulés, 180 secondes par desk,
35 secondes par appel, un tour de débat et de risque, zéro retry du connecteur.
Les limites du routeur Jarvis existant s'appliquent aussi ; une saturation
produit un état indisponible. Les réponses conservées dans le graphe sont
bornées à 6 000 caractères, les extraits des rôles à 700 caractères. Le pont
utilise les bornes de sortie de Jarvis, pas une promesse de 1 024 tokens par
appel. Une tentative échouée consomme également le jour ; les anciennes
preuves sont archivées. Prompts/mémoires amont temporaires, aucun apprentissage
ni changement automatique de stratégie. Les données brutes restent hors Git.

Les avis Buy/Sell sont consultatifs, jamais envoyés aux moteurs. Ils ne
remplacent ni les coûts stressés, ni les fenêtres indépendantes, ni les 126
séances futures requises. Aucun backtest IA ou gain causé par l'IA n'est
revendiqué. L'historique actions reste une fenêtre glissante de deux ans :
attendre ne suffit pas pour atteindre 600 séances. Son extension et ses biais
restent une tâche distincte ; aucun gel antérieur n'est antidaté.

## Arrêt existant et installation

Le 9 octobre à 14:48:23 UTC, le registre a fixé `paused_risk` pour drawdown,
avec dernière equity vérifiée **94,7907 EUR**, soit environ -5,21 % depuis
100 EUR. Le moteur a ensuite été stoppé ; ces chiffres sont un checkpoint,
pas une observation actuelle. Le registre, la base et les portefeuilles sont
préservés. Un déploiement et son rollback doivent conserver cet arrêt, avec
`up --no-deps supervisor` uniquement. Une base/API indisponible reste masquée.

Le code principal suit `scripts/deploy_oracle.py` et sa validation simulation.
L'installation optionnelle isolée suit `sudo -n python3 scripts/install_market_room.py`.
`--activate` configure le timer et lance la première tentative bornée. Aucune
configuration Freqtrade, clé exchange, ordre, portefeuille ni gel n'est modifié.

Validation source : 185 tests trading réussis ; paquet amont réellement
installé et graphe marché/news construit sans appel IA. Les preuves de
déploiement et de première analyse doivent être consignées après vérification.
