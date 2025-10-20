import logging

# Configurer le système de logs
logging.basicConfig(filename="logs/transactions.log", level=logging.WARNING, 
                    format="%(asctime)s - %(message)s")

def log_unauthorized_attempt(account_id):
    """Enregistre une tentative de virement non autorisée."""
    message = f"Tentative de virement non autorisée détectée pour le compte {account_id}."
    logging.warning(message)
    print(message)
