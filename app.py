import requests
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract
from dateutil import parser  # Import dateutil.parser for date parsing
import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///transactions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.String(200))
    price = db.Column(db.Float)
    category = db.Column(db.String(50))
    dateOfSale = db.Column(db.Date)

    def __repr__(self):
        return f"<Transaction {self.title}>"

# Function to seed data from the API
def seed_data():
    response = requests.get('https://s3.amazonaws.com/roxiler.com/product_transaction.json')
    data = response.json()
    for item in data:
        transaction = Transaction(
            title=item['title'],
            description=item['description'],
            price=item['price'],
            category=item['category'],
            dateOfSale=parser.parse(item['dateOfSale']).date()  # Use parser to handle datetime parsing
        )
        db.session.add(transaction)
    db.session.commit()

# Initialize the database and seed data
@app.before_first_request
def setup():
    db.create_all()
    if not Transaction.query.first():
        seed_data()

# API to list transactions with search and pagination
@app.route('/transactions', methods=['GET'])
def get_transactions():
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    month = request.args.get('month', '')

    query = Transaction.query
    if month:
        query = query.filter(extract('month', Transaction.dateOfSale) == datetime.datetime.strptime(month, '%B').month)
    
    if search:
        search = f"%{search}%"
        query = query.filter(
            (Transaction.title.like(search)) |
            (Transaction.description.like(search)) |
            (Transaction.price.like(search))
        )

    transactions = query.paginate(page, per_page, False).items
    return jsonify([{
        'title': t.title,
        'description': t.description,
        'price': t.price,
        'category': t.category,
        'dateOfSale': t.dateOfSale.isoformat()
    } for t in transactions])

# API for statistics
@app.route('/statistics', methods=['GET'])
def get_statistics():
    month = request.args.get('month')
    if not month:
        return jsonify({'error': 'Month is required'}), 400
    
    month_num = datetime.datetime.strptime(month, '%B').month
    
    total_sales = db.session.query(func.sum(Transaction.price)).filter(extract('month', Transaction.dateOfSale) == month_num).scalar()
    total_items = Transaction.query.filter(extract('month', Transaction.dateOfSale) == month_num).count()
    not_sold_items = Transaction.query.filter(extract('month', Transaction.dateOfSale) == month_num, Transaction.price == 0).count()
    
    return jsonify({
        'total_sales': total_sales,
        'total_items': total_items,
        'not_sold_items': not_sold_items
    })

# API for bar chart data
@app.route('/bar_chart', methods=['GET'])
def get_bar_chart():
    month = request.args.get('month')
    if not month:
        return jsonify({'error': 'Month is required'}), 400
    
    month_num = datetime.datetime.strptime(month, '%B').month
    
    ranges = [(0, 100), (101, 200), (201, 300), (301, 400), (401, 500),
              (501, 600), (601, 700), (701, 800), (801, 900), (901, float('inf'))]
    
    bar_chart_data = []
    for start, end in ranges:
        count = Transaction.query.filter(
            extract('month', Transaction.dateOfSale) == month_num,
            Transaction.price >= start,
            Transaction.price < (end if end != float('inf') else float('inf'))
        ).count()
        
        range_label = f'{start}-{end if end != float("inf") else "above"}'
        bar_chart_data.append({'range': range_label, 'count': count})
    
    return jsonify(bar_chart_data)

# API for pie chart data
@app.route('/pie_chart', methods=['GET'])
def get_pie_chart():
    month = request.args.get('month')
    if not month:
        return jsonify({'error': 'Month is required'}), 400
    
    month_num = datetime.datetime.strptime(month, '%B').month
    
    pie_chart_data = db.session.query(
        Transaction.category, func.count(Transaction.id)
    ).filter(
        extract('month', Transaction.dateOfSale) == month_num
    ).group_by(Transaction.category).all()
    
    return jsonify([{'category': c, 'count': count} for c, count in pie_chart_data])

# API to fetch combined data
@app.route('/combined_data', methods=['GET'])
def get_combined_data():
    month = request.args.get('month')
    if not month:
        return jsonify({'error': 'Month is required'}), 400
    
    # Get data from each API function
    transactions_response = get_transactions()
    statistics_response = get_statistics()
    bar_chart_response = get_bar_chart()
    pie_chart_response = get_pie_chart()
    
    # Combine the responses into a single JSON object
    combined_data = {
        'transactions': transactions_response.json,
        'statistics': statistics_response.json,
        'bar_chart': bar_chart_response.json,
        'pie_chart': pie_chart_response.json
    }
    
    return jsonify(combined_data)

if __name__ == "__main__":
    app.run(debug=True)
