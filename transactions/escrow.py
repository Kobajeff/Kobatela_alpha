import json

def handle_escrow(client, contractor, amount):
    """Bloque les fonds pour un contrat et simule leur déblocage."""
    print(f"Bloqué {amount} pour le contrat entre {client} et {contractor}.")
    # Charger les comptes certifiés
    with open("accounts.json", "r") as file:
        accounts = json.load(file)

    kobatela_account = accounts["kobatela_account"]
    print(f"L'argent est bloqué sur le compte Kobatela : {kobatela_account}")
    print("Attente de validation pour débloquer les fonds...")
