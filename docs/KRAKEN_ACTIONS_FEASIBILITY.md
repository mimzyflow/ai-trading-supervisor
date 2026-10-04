# Actions/ETF sur Kraken : faisabilité au 4 octobre 2026

Moussa souhaite idéalement utiliser Kraken, sa plateforme crypto, pour le bot
actions/ETF également. Kraken est donc la première piste à examiner. L'adaptateur
Alpaca Paper préparé constitue une autre possibilité, à choisir explicitement
si nécessaire ; il ne remplace pas automatiquement cette préférence.

## Produits et accès confirmés

| Produit | Situation documentée pour la France/EEE | Conséquence pour le bot |
| --- | --- | --- |
| Actions classiques US | Les guides Kraken citent explicitement la France parmi les pays EEE éligibles. Accès via Kraken Pro web/app et l'app Kraken ; pas via `kraken.com/c`. Compte personnel vérifié, questionnaire et acceptation des termes sont requis, puis revue par Kraken. | La disponibilité du produit est confirmée pour les clients français éligibles. Une API actions accessible au compte de Moussa et un environnement papier correspondant restent à confirmer. |
| xStocks, actions/ETF tokenisés | Un compte éligible et un questionnaire réussi sont requis en EEE. Les achats/ventes/conversions sont en fiat ; la documentation précise que le carnet et l'API xStocks sont indisponibles aux clients EEE, avec accès via Convert. | Le compte Kraken existant ne permet pas d'en déduire un bot xStocks exécutant des ordres API. Le blocage décrit par cette documentation doit être conservé. |

L'éligibilité du compte personnel de Moussa n'a pas encore été vérifiée. La
disponibilité dans l'interface ne prouve
pas l'accès automatisé, l'accès à tous les instruments ou une simulation papier.
Les guides officiels actualisés en août 2026 confirment la voie française pour
les actions classiques : cette analyse ne conclut donc pas à une impossibilité
générale. La confirmation restante pour le bot porte sur le produit exact,
l'accès API du compte et le mode papier.

L'onglet Chrome existant a été retrouvé pendant l'accompagnement et amené à la
connexion Kraken Pro. Moussa doit s'authentifier personnellement, répondre aux
questions requises et accepter les termes s'il souhaite poursuivre. Aucune
authentification réussie, approbation actions, connexion API ou simulation papier
n'est attestée à ce stade. Aucun ordre ni dépôt n'est requis pour cette revue.

## Simulation et code existant

Kraken décrit un environnement de test spot REST/WebSocket/FIX réservé aux
clients qualifiés, avec onboarding auprès de son équipe API. Il ne s'agit pas
d'un accès papier grand public acquis pour Moussa. Le paramètre `validate`
contrôle les détails d'un ordre et ne renvoie pas d'identifiant d'ordre ; il ne
produit pas un portefeuille, des exécutions et un registre prospectif complets.
La démo futures couvre des dérivés, un autre produit que les actions détenues
sans levier prévues ici.

Le code préparé dans `research_lab/paper_broker.py` fixe l'hôte Alpaca Paper et
des titres US. Le worker actions attend un bundle `stock`/`etf` et aucun
exécuteur prospectif n'est encore raccordé. Le simulateur traite les dividendes
comme des flux en espèces ; les xStocks réinvestissent leur bénéfice économique
par rebasing/multiplicateur et ne confèrent pas les mêmes droits qu'une action.
Leurs prix, calendrier, lots, frais, spreads et ajustements doivent donc être
modélisés et vérifiés séparément. Changer seulement l'hôte ou le symbole serait
insuffisant.

Le protocole actuel exige 600 séances de développement. Le lancement Kraken
xStocks date du 30 juin 2025, soit 461 jours jusqu'au 4 octobre 2026 : un
historique journalier propre à cette plateforme ne peut déjà couvrir 600
séances. C'est une déduction des dates, pas une mesure de données téléchargées.
Un historique du titre sous-jacent ne constitue pas une preuve d'exécution du
token. Le seuil et les 126 séances de contrôle futur du protocole existant ne
sont pas modifiés par cette analyse.

## Prochaine étape utile

1. Moussa s'authentifie sur Kraken Pro, vérifie son éligibilité et effectue les
   réponses personnelles/acceptations nécessaires à l'accès actions. Confirmer
   ensuite le produit proposé à son compte français. Pour le bot, obtenir
   une confirmation explicite de l'API, du périmètre et du mode papier utilisable.
   Aucun identifiant API n'est à demander avant cette confirmation.
2. Choisir un ou deux instruments précisément identifiés, leur forme juridique,
   leur devise et le budget virtuel. Des actions classiques, des ETF UCITS et
   leurs représentations tokenisées ne sont pas interchangeables.
3. Si une voie Kraken adaptée est confirmée, préparer un adaptateur distinct,
   une collecte de données vérifiées et la recette papier avant toute exécution.
   Sinon, choisir explicitement entre recherche/simulation locale sans ordre
   et examen d'un autre courtier papier. Aucune bascule automatique vers Alpaca.

Une simulation locale sur données publiques est une piste de recherche limitée,
sans compte ni argent réel. Elle ne prouve ni l'éligibilité à trader sur Kraken,
ni une stratégie validée, ni la disponibilité de l'API finale. Aucun compte,
clé ou ordre n'a été connecté lors de cette analyse en lecture seule.

## Sources officielles consultées le 4 octobre 2026

- [Kraken : actions classiques US pour les clients EEE, annonce du 18 août 2026](https://blog.kraken.com/product/equities/announcing-us-listed-stock-trading-for-eea-customers)
- [Kraken : commencer avec les actions, France et plateformes, guide du 18 août 2026](https://support.kraken.com/articles/getting-started-with-equities)
- [Kraken : accès actions sur Kraken Pro, questionnaire et termes, guide du 17 août 2026](https://support.kraken.com/articles/unlock-stocks-trading-on-kraken-pro)
- [Kraken : disponibilité xStocks et exigences EEE, article daté du 18 juin 2026](https://support.kraken.com/gb/articles/xstocks-availability)
- [Kraken : FAQ API, environnement qualifié et paramètre validate](https://support.kraken.com/articles/advanced-api-faq)
- [Kraken : FAQ xStocks, rebasing et dividendes, article daté du 18 septembre 2026](https://support.kraken.com/articles/xstocks-faq)
- [Kraken : lancement xStocks du 30 juin 2025](https://blog.kraken.com/product/xstocks/tokenized-equities-now-available)
