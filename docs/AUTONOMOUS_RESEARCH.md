# Recherche autonome et extension actions/ETF

Le système reste un laboratoire. Il ne garantit jamais une amélioration de la
rentabilité. Une nouvelle variante peut être rejetée, et une règle validée sur
une période peut ensuite perdre de l'argent. Le paramétrage n'est pas un instinct
de survie : les limites sont imposées par du code séparé des stratégies.

## Ce qui fonctionne sans compte supplémentaire

- `research_lab.worker` vérifie la simulation Kraken existante toutes les cinq
  minutes et collecte les dernières bougies quotidiennes BTC/EUR et ETH/EUR au
  plus une fois par jour réussi. Aucune clé exchange et aucun appel IA payant.
- Les bougies clôturées sont conservées. Doublons, lacunes quotidiennes,
  révisions d'historique, valeurs invalides, volumes nuls et bougies ouvertes
  interrompent l'expérience au lieu d'inventer une donnée.
- Quatre variantes de tendance/breakout sont évaluées avec portefeuille 100
  unités, deux allocations plafonnées à 20, coûts des deux côtés, glissement,
  référence cash et référence passive à allocation comparable.
- Les périodes de sélection font partie du développement. Une candidate
  choisie est figée avec empreintes des données, des paramètres et du code.
  Avant tout contrôle, les bougies de développement et les caractéristiques
  des instruments doivent conserver leur empreinte. Un historique modifié,
  tronqué ou un ancien plan sans empreinte vérifiable refuse le contrôle.
  Son contrôle utilise ensuite 126 séances qui commencent **après** la date de
  gel. Les mois suivants ne réinitialisent pas ce délai.
- Le contrôle est réservé dans SQLite avant l'essai, une seule fois par fenêtre
  et périmètre. Un plantage après réservation ne permet pas de retester la même
  fenêtre jusqu'à obtenir un bon chiffre. Changer le code nécessite un nouveau plan.
- Critères expérimentaux : profit net supérieur au cash et au passif d'au moins
  0,1 point, PF ≥1,2, baisse maximale ≤5 %, au moins cinq clôtures dans le contrôle
  et 30 au total développement/contrôle, coûts stressés positifs, concentration
  limitée pour les portefeuilles à deux actifs. Ce sont des filtres de recherche,
  pas une certification financière ni une garantie statistique.
- La portée est un univers figé à l'avance, suivi pendant la fenêtre future.
  Cela ne reconstruit pas un univers historique de toutes les cryptomonnaies et
  ne valide pas les anciennes conclusions small/mid-cap.
- Un résultat `paper_candidate_passed` reste un profil de recherche. Il ne
  remplace pas automatiquement la baseline Freqtrade et n'active jamais le réel.

## Arrêt avant zéro et conservation

La baisse du portefeuille est mesurée par rapport au maximum observé, avec un
seuil de 5 %. Avant un arrêt, le garde relit le mode dans Docker **et** l'API
locale : DRY-RUN réel, Kraken spot EUR, aucune clé Kraken injectée. Il peut alors
arrêter seulement `ai-trading-freqtrade`. Il n'envoie aucun ordre API, ne ferme
aucune position réelle, ne détruit pas le code et conserve base et preuves.

L'arrêt est mémorisé ; une remontée ultérieure ne relance pas le bot. À zéro,
le profil est archivé comme `retired`. Une reprise exige une revue du problème
et un changement explicite de l'état, jamais une recharge automatique d'argent.
Un arrêt déjà mémorisé est retenté après une erreur, même si le rapport suivant
est invalide ; chaque tentative garde la vérification actuelle Docker/API avant
tout arrêt. Une erreur d'observation et une erreur d'arrêt sont distinguées.
Le seuil n'est pas une garantie de perte maximale : mouvements brusques,
glissement et délais entre observations peuvent conduire à une perte supérieure.

## La règle ×10 et les descendants

`Registry.create_child` ne reçoit que des preuves **papier prospectives** liées
au bot concerné : parent validé, 126 séances, 30 clôtures, zéro position ouverte,
aucun apport externe, capital final ≥10 fois l'initial, gain réalisé ≥9 fois
l'initial, observation récente. Un backtest, un dépôt ou un gain latent ne compte pas.

La fonction crée un profil `research_only`, pas un compte courtier ni une instance
financée. Elle impose trois profils maximum, profondeur deux, un enfant par parent
et partage d'une capacité virtuelle globale de 100. Les enfants héritent d'une
description de stratégie, jamais de clés ou de pouvoirs d'administration.
Les candidats peuvent varier des paramètres autorisés ; ils ne peuvent pas
changer la fonction de score, modifier leurs prix, lever les limites ou exécuter
du Python arbitraire. La performance future reste inconnue.

L'activation de cette fabrique exige une véritable chaîne de preuves prospectives.
La baseline actuelle n'est pas validée ; aucun descendant opérationnel n'est créé.

## Actions et ETF : moteur distinct, connexion restant à faire

Freqtrade se décrit comme un bot de cryptomonnaies. Le moteur actions/ETF est
donc distinct : `scripts/simulate_equities.py` et `research_lab.engine`.

Le fichier `research_state/equities.bundle.json` contient un ou deux instruments
`stock`/`etf`, dans la même monnaie EUR ou USD. Il précise identifiant instrument,
lot de négociation, prix **non ajustés**, ouvertures/clôtures UTC de vraies séances,
OHLCV, splits effectifs et dividendes par action avec date de paiement. Une créance
de dividende contribue à la valeur mais n'est pas disponible avant paiement.
Les historiques utilisés dans les signaux sont ajustés uniquement des splits
déjà effectifs. Calendrier, événements et univers doivent être vérifiés pour
qualifier une candidate. Pas de conversion FX implicite ni de fraction supposée.

Champs principaux :

```json
{
  "schema_version": 1,
  "currency": "EUR",
  "calendar_verified": false,
  "corporate_actions_verified": false,
  "historical_universe_verified": false,
  "assets": [{
    "id": "IDENTIFIANT_INSTRUMENT",
    "asset_class": "etf",
    "currency": "EUR",
    "price_basis": "raw",
    "lot_size": 1,
    "bars": []
  }]
}
```

Une barre fournit `open_at`, `close_at`, `open`, `high`, `low`, `close`, `volume`.
Événement optionnel : `split_ratio`, ou `dividend_per_share` avec
`dividend_paid_at`. Le squelette ci-dessus n'est pas un historique exploitable.

Le modèle teste une commission de 0,1 % avec minimum de 1 unité monétaire par
côté et un glissement de 0,1 % ; stress glissement 0,25 %. Ce sont des scénarios,
pas les frais vérifiés d'un courtier. Un capital de 100 et une allocation de 20
peuvent être incompatibles avec le prix d'une part entière ou économiquement
inefficaces après commission. Le simulateur produit alors zéro ordre faisable.

`research_lab.paper_broker.PaperBroker` prépare Alpaca Paper pour des titres US :
hôte fixé à `paper-api.alpaca.markets`, redirections refusées, marchés ouverts,
deux instruments autorisés maximum, achats limités à 20 et exposition à 40 en
comptant les ordres en attente. Vente limitée aux titres détenus, sans short,
ordres limités entiers uniquement, identifiant unique et rapprochement après
timeout. Aucune API de financement et aucune URL live ne sont exposées.

**Aucun ordre courtier n'est activé par le worker.** Un compte Paper Only, ses
clés privées, un univers défini et les données/licences sont nécessaires pour
une vraie recette API et pour connecter un exécuteur prospectif. La fabrique
ne doit jamais assimiler les 100 000 USD par défaut d'Alpaca à un portefeuille
expérimental de 100. L'offre papier US ne prouve pas l'éligibilité d'un résident
français à des instruments ou à une offre live européenne/ETF UCITS.

Pour un besoin actions européennes/ETF UCITS, vérifier séparément un courtier
comme IBKR, ses contrats, autorisations, flux, authentification et commissions.
Aucun compte, abonnement de données ou dépôt n'a été ouvert par ce correctif.

## Exploitation Oracle

La [checklist de reprise avec Moussa](RETURN_CHECKLIST.md) distingue les choix,
comptes et identifiants nécessaires des travaux techniques encore à réaliser.
`scripts/check_paper_readiness.py` prépare une vérification uniquement en lecture
de l'état initial du compte papier ; elle n'active aucun ordre. Les appels publics
directs d'ordre passent désormais aussi par les limites complètes de positions,
ordres en attente, quantité entière et identifiant unique du connecteur.

Le déploiement installe `trading-research.service` et `trading-research.timer`.
Le service a un seul exécuteur, quota CPU 25 %, mémoire 256 Mo, 24 tâches maximum,
timeout 180 s et écrit uniquement état/reports ; le code est en lecture seule
pendant son exécution. Il utilise le Docker local pour le seul arrêt protégé.
Ce privilège est limité par des noms/commandes fixes, sans socket donné aux stratégies.

```sh
sudo systemctl status trading-research.timer
sudo journalctl -u trading-research.service -n 20 --no-pager
sudo cat /home/ubuntu/ai-trading-supervisor/user_data/reports/autonomy.json
sudo systemctl stop trading-research.timer
```

`research_state/` et sa base restent hors Git. `autonomy.json` indique risques,
phase de recherche, erreurs, profils et attente de données actions/ETF. Le rapport
Freqtrade reprend un résumé borné. Un succès technique ne constitue pas une
preuve de connexion broker, de rentabilité ou de publication GitHub automatique.
Les marqueurs quotidiens corrompus sont signalés puis recalculés si les données
restent disponibles. La base des preuves et les réservations de contrôle ne sont
pas réinitialisées ; une erreur du marqueur n'empêche plus le rapport de risque.

Sources officielles consultées le 3 octobre 2026 :

- [Freqtrade, périmètre crypto](https://www.freqtrade.io/en/stable/)
- [Kraken OHLC, 720 bougies et dernière bougie ouverte](https://docs.kraken.com/api-reference/market-data/get-ohlc-data)
- [Alpaca Paper, accès mondial et limites du simulateur](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca, ordre et client_order_id](https://docs.alpaca.markets/us/reference/postorder)
- [IBKR Web API, authentification et accès](https://www.interactivebrokers.com/docs/web-api/introduction)
