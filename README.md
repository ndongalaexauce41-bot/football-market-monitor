# ⚽ FOOTBALL MARKET MONITOR

Application Streamlit de surveillance pré-match des marchés football.

## Fonctionnalités

- saisie d'une **URL publique** comme source principale ;
- **nouvelle récupération** à chaque recherche ou actualisation ;
- sélection de la **date cible** : aujourd'hui ou date personnalisée ;
- identification de **tous les matchs disponibles** pour la date cible ;
- recherche du marché **Double chance 12** ;
- récupération de la **cote réellement publiée** ;
- comparaison avec un **seuil configurable** ;
- affichage en deux vues : **tous les matchs** et **matchs atteignant le seuil** ;
- affichage de la **fraîcheur des données** et de l'horodatage de récupération ;
- gestion explicite des erreurs sans inventer de données.

## Fichiers

- `app.py`
- `requirements.txt`
- `README.md`

## Dépendances

```txt
streamlit
pandas
requests
beautifulsoup4
streamlit-autorefresh
```

## Lancer en local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Déploiement sur Streamlit Community Cloud

1. créer un dépôt Git contenant `app.py`, `requirements.txt` et `README.md` ;
2. pousser le dépôt sur GitHub ;
3. créer une nouvelle application dans Streamlit Community Cloud ;
4. sélectionner le dépôt et le fichier principal `app.py`.

## Notes importantes

- L'application n'effectue **aucune mise**, **aucune transaction** et **aucune automatisation de pari**.
- Elle utilise uniquement des méthodes d'accès autorisées basées sur `requests` et `BeautifulSoup`.
- Si la source est inaccessible, vide, modifiée ou non compatible, l'application affiche une erreur explicite.
- Si la structure de la source n'est pas reconnue, un **adaptateur spécifique** peut être nécessaire.
- Aucune donnée n'est inventée : si une information n'est pas réellement récupérée, l'application affiche `❌ Donnée indisponible` ou un message d'erreur adapté.
