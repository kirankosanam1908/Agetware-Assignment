
import json
import os
import math
from datetime import datetime
from flask import Flask, request, jsonify

# --- Basic Setup ---
app = Flask(__name__)
DATA_FILE = "bank_data.json"

# --- Data Persistence Helper Functions ---
def load_data():
    """Loads data from the JSON file. Creates the file if it doesn't exist."""
    if not os.path.exists(DATA_FILE):
        # Initialize with an empty structure
        return {"loans": {}, "customers": {}, "next_loan_id": 1}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    """Saves data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- Core Bank Logic Helpers ---
def get_loan_details(loan_id, data):
    """A helper to calculate dynamic loan details like amount paid and EMIs left."""
    loan = data['loans'].get(loan_id)
    if not loan:
        return None

    amount_paid = sum(p['amount'] for p in loan['payments'])
    balance_amount = loan['total_amount'] - amount_paid
    
    # Ensure we don't divide by zero if EMI is 0
    if loan['emi_amount'] > 0:
        emis_left = math.ceil(balance_amount / loan['emi_amount'])
    else:
        emis_left = 0

    return {
        "principal": loan['principal'],
        "total_amount": loan['total_amount'],
        "emi_amount": loan['emi_amount'],
        "total_interest": loan['total_interest'],
        "amount_paid": round(amount_paid, 2),
        "balance_amount": round(balance_amount, 2),
        "emis_left": max(0, emis_left) # Don't show negative EMIs
    }


# --- API Endpoints ---

@app.route('/lend', methods=['POST'])
def lend_money():
    """
    Creates a new loan for a customer.
    Input: { "customer_id": str, "amount": float, "years": int, "rate": float }
    """
    req_data = request.get_json()
    customer_id = req_data.get('customer_id')
    principal = float(req_data.get('amount'))  # P
    years = int(req_data.get('years'))        # N
    rate = float(req_data.get('rate')) / 100.0 # R (assuming rate is in %)

    # Basic Validation
    if not all([customer_id, principal > 0, years > 0, rate > 0]):
        return jsonify({"error": "Invalid or missing parameters."}), 400

    # Calculations as per the problem description
    interest = principal * years * rate
    total_amount = principal + interest
    emi_amount = total_amount / (years * 12)

    data = load_data()
    loan_id = str(data['next_loan_id'])
    
    # Create the new loan object
    new_loan = {
        "customer_id": customer_id,
        "principal": principal,
        "years": years,
        "rate": rate,
        "total_interest": round(interest, 2),
        "total_amount": round(total_amount, 2),
        "emi_amount": round(emi_amount, 2),
        "payments": [] # Start with no payments
    }
    
    # Update data structure
    data['loans'][loan_id] = new_loan
    data['next_loan_id'] += 1
    
    # Add loan to customer's record
    if customer_id not in data['customers']:
        data['customers'][customer_id] = {"loan_ids": []}
    data['customers'][customer_id]['loan_ids'].append(loan_id)
    
    save_data(data)

    return jsonify({
        "loan_id": loan_id,
        "message": "Loan approved successfully.",
        "total_amount_to_pay": new_loan['total_amount'],
        "monthly_emi": new_loan['emi_amount']
    }), 201


@app.route('/payment', methods=['POST'])
def make_payment():
    """
    Records a payment for a specific loan.
    Input: { "loan_id": str, "amount": float }
    """
    req_data = request.get_json()
    loan_id = req_data.get('loan_id')
    amount = float(req_data.get('amount'))

    if not loan_id or amount <= 0:
        return jsonify({"error": "Loan ID and a positive amount are required."}), 400
        
    data = load_data()
    
    if loan_id not in data['loans']:
        return jsonify({"error": "Loan not found."}), 404

    loan = data['loans'][loan_id]
    details = get_loan_details(loan_id, data)

    if details['balance_amount'] <= 0:
        return jsonify({"message": "This loan is already fully paid."}), 200

    if amount > details['balance_amount']:
        amount = details['balance_amount'] # Prevent overpayment
        
    payment_record = {
        "amount": round(amount, 2),
        "date": datetime.utcnow().isoformat()
    }
    
    loan['payments'].append(payment_record)
    save_data(data)
    
    return jsonify({
        "message": "Payment recorded successfully.",
        "loan_id": loan_id,
        "amount_paid": amount
    }), 200


@app.route('/ledger/<loan_id>', methods=['GET'])
def get_ledger(loan_id):
    """
    Returns the transaction history and current status for a single loan.
    """
    data = load_data()
    if loan_id not in data['loans']:
        return jsonify({"error": "Loan not found."}), 404
    
    loan = data['loans'][loan_id]
    details = get_loan_details(loan_id, data)

    response = {
        "loan_id": loan_id,
        "customer_id": loan['customer_id'],
        "balance_amount": details['balance_amount'],
        "monthly_emi": details['emi_amount'],
        "emis_left": details['emis_left'],
        "transactions": loan['payments']
    }
    
    return jsonify(response), 200

@app.route('/overview/<customer_id>', methods=['GET'])
def get_account_overview(customer_id):
    """
    Returns an overview of all loans for a specific customer.
    """
    data = load_data()
    if customer_id not in data['customers']:
        return jsonify({"error": "Customer not found."}), 404
        
    customer_loans = data['customers'][customer_id]['loan_ids']
    overview_list = []
    
    for loan_id in customer_loans:
        details = get_loan_details(loan_id, data)
        if details:
            loan_summary = {
                "loan_id": loan_id,
                "principal_amount": details['principal'],
                "total_amount": details['total_amount'],
                "emi_amount": details['emi_amount'],
                "total_interest": details['total_interest'],
                "amount_paid_till_date": details['amount_paid'],
                "emis_left": details['emis_left']
            }
            overview_list.append(loan_summary)

    return jsonify({"customer_id": customer_id, "loans": overview_list}), 200

# --- Main Execution ---
if __name__ == '__main__':
    app.run(debug=True, port=5001)
