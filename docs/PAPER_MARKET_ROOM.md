# Expérience virtuelle de 100 EUR par bot

Décision explicite de Moussa du 9 octobre 2026 : 100 EUR pour chacun des deux
bots, aucun arrêt de portefeuille ni stop de perte par position. Cette décision
est enregistrée dans `simulation-policy.json`, identifiant
`market-room-100eur-20261009`. Le déploiement doit vérifier l'image native
Freqtrade avant toute activation ; sa preuve est distincte de ces instructions.

## Capital et conservation

- Crypto : nouveau compte DRY-RUN de 100 EUR, stratégie `MoussaMarketRoom`,
  base `trades-market-room-100eur-20261009.dryrun.sqlite`. La base V2
  `tradesv3.dryrun.sqlite` et ses pertes restent conservées et séparées.
- Actions : nouveau compte BROKERLESS_PAPER, fichier
  `research_state/equity_market-room-100eur-20261009.json`. Les 100 EUR sont
  convertis en USD avec la référence BCE datée réellement collectée. Sans taux
  récent valide, aucune conversion 1:1 ni valeur EUR inventée.
- Les anciens quatre comptes actions USD continuent comme comparateurs avec
  leurs règles originales. Ils ne font pas partie des 200 EUR de cette expérience.
  Les recherches historiques et critères V3 ne sont pas réécrits.
- Les nouvelles positions actions commencent après l'activation : aucune
  séance antérieure n'est rejouée pour fabriquer un rendement.

## Influence de la salle

Un avis TradingAgents complet, épinglé à la version amont et à cette politique,
daté de moins de 36 heures, ajuste les achats : Buy ×2, Overweight ×1,5,
Hold ×1, Underweight ×0,5. Sell bloque les nouvelles entrées et demande une
sortie stratégique. La crypto reste limitée au cash virtuel et à 20 EUR par
achat ; les actions gardent leurs frais, glissement et allocation en USD.
L'avis concerne chaque desk, pas une recommandation par titre. Aucun levier,
emprunt ni raccordement courtier n'est ajouté. Une analyse indisponible ou
périmée utilise la stratégie technique de base, avec état `fallback` visible.

Les prix et rendements fournis aux agents proviennent des barres déjà clôturées,
datées et valides du collecteur. Nouvelles, fondamentaux et sentiment absents
sont déclarés comme tels. Les avis ne démontrent pas une amélioration de rendement.
Les états autorisés et les multiplicateurs sont les seuls inputs du moteur ;
aucun texte du modèle n'est exécuté ni converti en commande.

Les stops statiques, les stops suiveurs et StoplossGuard sont désactivés dans
la nouvelle expérience. Freqtrade impose un nombre `stoploss` : il vaut -1,
et le callback DRY-RUN refuse toutes les sorties déclenchées par ces stops.
Le worker surveille la baisse sans arrêt, même à 85 % ou à épuisement du capital.
Les ventes sur signal technique, prise de bénéfice, durée ou avis Sell restent
possibles, y compris à perte. Les contrôles de données et de mode simulation
restent nécessaires pour que les résultats aient un sens.

## Alertes et rapports

Le superviseur collecte toutes les cinq minutes. Un nouveau palier de perte
de 5 points du capital initial produit un événement durable `notify_only`
dans `user_data/reports/loss-alerts.json`, sans arrêter le bot. Le palier est
dédupliqué après redémarrage. Une chute directe de 0 à 85 % génère le palier 85 %.
Le tableau Jarvis et la surveillance Codex lisent ce journal. Le planificateur
Codex dépend du poste disponible ; collecte Oracle et journal restent autonomes.

Une tentative IA au plus par jour et par politique, réservée avant l'appel,
16 appels et 180 secondes maximum par desk, aucun retry automatique. La nouvelle
politique possède sa réservation distincte pour ne pas réutiliser l'ancien avis
produit sous la limite à 5 %. L'ancienne réservation et les rapports sont conservés.
Le pont Jarvis garde ses quotas et fournisseurs actuels ; budget propre 0 EUR
ne signifie pas que le fournisseur existant est gratuit.

Exception de maintenance explicite : `--repair-after-bridge-reload` autorise
une seule réparation manuelle après deux échecs HTTP 503 au premier appel,
avec preuve systemd d'un rechargement du relais postérieur à ces échecs.
Cette option exige root, n'est jamais passée par le timer ni la surveillance,
conserve la réservation du jour et archive le rapport échoué. Les appels et
caractères déjà consommés sont déduits des mêmes plafonds 16 / 240 000.
Une seconde réparation est refusée, y compris après un nouveau crash.

Jarvis : **Plus → Trading IA**. Sources privées fixes : `/api/trading`,
`/api/trading/report` et `/api/trading/room-report`, avec session obligatoire.
Les montants crypto EUR, les valeurs actions USD, la conversion EUR datée et
les comparateurs doivent être lus séparément. Zéro transaction ne valide rien.

Tests : baisse 100 → 15 → 100 sans stop, épuisement sans arrêt, réservation et
archives conservées, refus du mode réel, conseil périmé/ancien ignoré, taux BCE
récent obligatoire et alertes durables. Le validateur de déploiement utilise
l'image Freqtrade épinglée sans réseau ni données opérationnelles montées.
