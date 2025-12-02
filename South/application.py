from flask import Flask, request, session, redirect, url_for, render_template, jsonify
import boto3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Initialize the Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Initialize DynamoDB resource
# Since you ran 'aws configure', this will automatically use the keys you entered!
dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')

# Define DynamoDB tables
user_table = dynamodb.Table('UserTable')
wishlist_table = dynamodb.Table('WishlistTable')


# Home route
@app.route('/')
def home():
    logged_in = 'email' in session
    return render_template('home.html', logged_in=logged_in)

# User registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        # Store user data in DynamoDB
        user_table.put_item(
            Item={
                'email': email,
                'username': username,
                'hashed_password': hashed_password,
                'login_count': 0
            }
        )
        return redirect(url_for('login'))
    return render_template('register.html')

# User login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Fetch user details from DynamoDB
        response = user_table.get_item(Key={'email': email})
        user = response.get('Item')

        if user and check_password_hash(user['hashed_password'], password):
            # Update login count
            user_table.update_item(
                Key={'email': email},
                UpdateExpression='SET login_count = login_count + :val',
                ExpressionAttributeValues={':val': 1}
            )
            session['email'] = email
            session['username'] = user['username']  # Store the username
            return redirect(url_for('user_dashboard'))
        else:
            return 'Invalid credentials! Please try again.'
    return render_template('login.html')

# User dashboard route
@app.route('/user_dashboard')
def user_dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    return render_template('user_dashboard.html')

# Add to wishlist route
@app.route('/add_to_wishlist', methods=['POST'])
def add_to_wishlist():
    if 'email' not in session:
        return redirect(url_for('login'))

    item_id = request.json['item_id']
    item_name = request.json['item_name']
    item_details = request.json['item_details']

    # Add item to WishlistTable in DynamoDB
    wishlist_table.put_item(
        Item={
            'email': session['email'],
            'item_id': item_id,
            'item_name': item_name,
            'item_details': item_details,
            'added_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')  # Store the current UTC date
        }
    )
    return jsonify({'success': True, 'message': 'Item added to wishlist'})

# View wishlist route
@app.route('/wishlist')
def wishlist():
    if 'email' not in session:
        return redirect(url_for('login'))

    # Retrieve wishlist items from DynamoDB for the logged-in user
    response = wishlist_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(session['email'])
    )
    wishlist_items = response.get('Items', [])  # Ensure all items are passed to the frontend

    return render_template('wishlist.html')

@app.route('/wishlist_data')
def wishlist_data():
    if 'email' not in session:
        return jsonify({'wishlist': []})

    response = wishlist_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(session['email'])
    )
    wishlist_items = response.get('Items', [])
    return jsonify({'wishlist': wishlist_items})


# Route to remove an item from the wishlist
@app.route('/remove_from_wishlist', methods=['POST'])
def remove_from_wishlist():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    item_id = request.json.get('item_id')

    if not item_id:
        return jsonify({'success': False, 'message': 'Item ID not provided'})

    # Remove the item from WishlistTable in DynamoDB
    try:
        wishlist_table.delete_item(
            Key={
                'email': session['email'],
                'item_id': item_id
            }
        )
        return jsonify({'success': True, 'message': 'Item removed from wishlist'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

# Virtual exhibition route
@app.route('/virtual_exhibition', methods=['GET', 'POST'])
def virtual_exhibition():
    if request.method == 'POST':
        if 'email' not in session:
            return jsonify({'success': False, 'message': 'User not logged in. Please log in to add items to your wishlist.'})

        item_data = request.json
        item_name = item_data.get('name')
        item_metal = item_data.get('metal')
        item_weight = item_data.get('weight')
        item_price = item_data.get('price')
        item_image = item_data.get('image')

        if not all([item_name, item_metal, item_weight, item_price, item_image]):
            return jsonify({'success': False, 'message': 'Invalid item data. Please try again.'})

        try:
            wishlist_table.put_item(
                Item={
                    'email': session['email'],
                    'item_id': item_name,
                    'item_name': item_name,
                    'item_details': f"Metal: {item_metal}, Weight: {item_weight}, Price: {item_price}",
                    'added_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    'item_image': item_image
                }
            )
            return jsonify({'success': True, 'message': f'Item "{item_name}" added to wishlist successfully!'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error adding item to wishlist: {str(e)}'})
    
    # ✅ Render exhibition page on GET
    return render_template('virtual_exhibition.html')



# Quiz page and submission
@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    if request.method == 'POST':
        score = int(request.form.get('score', 0))
        if score >= 12:
            session['won_quiz'] = True  # Set the status for quiz win
        else:
            session['won_quiz'] = False
        return redirect(url_for('user_dashboard'))
    return render_template('quiz.html')


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'email' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        # Retrieve checkout items from the session
        checkout_items = session.get('checkout_items', [])
        for item in checkout_items:
            if 'quantity' not in item:
                item['quantity'] = 1  # Default quantity
            item['total_price'] = int(item['price'].replace(',', '').split(' ')[0]) * item['quantity']

        # Calculate subtotal and total prices
        subtotal = sum(item['total_price'] for item in checkout_items)
        discount = session.get('discount', 0)
        total_price = subtotal - discount

        # Update session with calculated values
        session['checkout_items'] = checkout_items
        session['subtotal'] = subtotal
        session['final_price'] = total_price
        session.modified = True

        return render_template(
            'checkout.html',
            checkout_items=checkout_items,
            subtotal=subtotal,
            discount=discount,
            total_price=total_price,
        )

    if request.method == 'POST':
        data = request.json

        if data['action'] == 'apply_coupon':
            # Handle coupon application
            coupon_code = data.get('coupon_code', '').upper()
            checkout_items = session.get('checkout_items', [])
            subtotal = sum(
                int(item['price'].replace(',', '').split(' ')[0]) * item.get('quantity', 1)
                for item in checkout_items
            )

            discount = 0
            if coupon_code == 'WON10':
                discount = subtotal * 0.10
            elif coupon_code == 'WON20':
                discount = subtotal * 0.20
            elif coupon_code == 'WON30':
                discount = subtotal * 0.30

            total_price = subtotal - discount
            session['discount'] = discount
            session['final_price'] = total_price
            session.modified = True

            return jsonify({'success': True, 'discount': discount, 'total_price': total_price})

        elif data['action'] == 'update_quantity':
            # Handle quantity updates
            item_name = data['item_name']
            quantity = int(data['quantity'])
            checkout_items = session.get('checkout_items', [])

            for item in checkout_items:
                if item['name'] == item_name:
                    item['quantity'] = quantity
                    item['total_price'] = int(item['price'].replace(',', '').split(' ')[0]) * quantity
                    break

            subtotal = sum(item['total_price'] for item in checkout_items)
            discount = session.get('discount', 0)
            total_price = subtotal - discount

            session['checkout_items'] = checkout_items
            session['subtotal'] = subtotal
            session['final_price'] = total_price
            session.modified = True

            return jsonify({'success': True, 'total_price': total_price})

        elif data['action'] == 'remove':
            # Handle item removal
            item_name = data['item_name']
            checkout_items = session.get('checkout_items', [])
            updated_checkout_items = [item for item in checkout_items if item['name'] != item_name]

            subtotal = sum(
                int(item['price'].replace(',', '').split(' ')[0]) * item.get('quantity', 1)
                for item in updated_checkout_items
            )
            discount = session.get('discount', 0)
            total_price = subtotal - discount

            session['checkout_items'] = updated_checkout_items
            session['subtotal'] = subtotal
            session['final_price'] = total_price
            session.modified = True

            return jsonify({'success': True, 'message': f"Item {item_name} removed from checkout!", 'total_price': total_price})

        elif data['action'] == 'finalize':
            # Finalize checkout and save order items
            session['order_items'] = session.get('checkout_items', [])
            session.modified = True

            return jsonify({'success': True, 'redirect': url_for('order')})

        return jsonify({'success': False, 'message': 'Invalid action!'})

@app.route('/checkout_items', methods=['GET'])
def checkout_items():
    # Retrieve checkout items for rendering on the frontend
    if 'email' not in session:
        return jsonify({'checkout_items': []})
    return jsonify({'checkout_items': session.get('checkout_items', [])})


@app.route('/add_to_checkout', methods=['POST'])
def add_to_checkout():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    item_id = request.json.get('item_id')
    if not item_id:
        return jsonify({'success': False, 'message': 'Item ID missing'})

    # Fetch the item from wishlist
    try:
        response = wishlist_table.get_item(
            Key={'email': session['email'], 'item_id': item_id}
        )
        item = response.get('Item')
        if not item:
            return jsonify({'success': False, 'message': 'Item not found in wishlist'})

        # Prepare item for checkout session
        checkout_item = {
            'item_id': item['item_id'],
            'item_name': item['item_name'],
            'price': item['item_details'].split('Price: ')[-1],  # e.g., "3,50,000 INR"
            'image': item.get('item_image', ''),
            'details': item.get('item_details', ''),
            'quantity': 1
        }

        # Initialize or update checkout session
        checkout_items = session.get('checkout_items', [])
        existing = next((i for i in checkout_items if i['item_id'] == item_id), None)

        if not existing:
            checkout_items.append(checkout_item)
            session['checkout_items'] = checkout_items
            session.modified = True

        return jsonify({'success': True, 'message': 'Item added to checkout'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/order', methods=['GET', 'POST'])
def order():
    if 'email' not in session:
        return redirect(url_for('login'))

    # Get finalized order details from session
    order_items = session.get('order_items', [])
    final_price = session.get('final_price', 0)

    if request.method == 'POST':
        # Handle order placement
        full_name = request.form.get('first_name') + " " + request.form.get('last_name')
        address = f"{request.form.get('street_address')}, {request.form.get('city')}, {request.form.get('state')}, {request.form.get('postal_code')}"
        payment_method = request.form.get('payment_method')

        # Process the order
        print(f"Order placed by {full_name} to {address} with payment method {payment_method}")

        # Clear session after order is placed
        session.pop('order_items', None)
        session.pop('final_price', None)
        session.pop('discount', None)
        session.modified = True

        # Pass a flag to the frontend indicating that the order was successfully placed
        return render_template('order.html', order_completed=True)

    # Render the order summary page
    return render_template('order.html', checkout_items=order_items, total_price=final_price, discount=session.get('discount', 0), order_completed=False)


# User logout route
@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect(url_for('login'))

# Run the Flask app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80,debug=True)
