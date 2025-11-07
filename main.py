import json
from transactions.alerts import log_unauthorized_attempt
from transactions.escrow import handle_escrow

def main():
    print("Bienvenue dans le système Kobatela Backend!")
    # Exemple de test des modules
    log_unauthorized_attempt("12345")
    handle_escrow("Client A", "Contractor B", 1000)

if __name__ == "__main__":
    main()
