from flask import Flask, render_template, redirect, url_for, request, session, flash
from passlib.hash import sha256_crypt
import pymysql
import requests
from datetime import datetime, timedelta

app = Flask(__name__)


@app.route('/')
def root():
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('home'))
    else:
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor()
        sql = "SELECT ID, USERNAME, PASSWORD FROM USERS WHERE USERNAME = '" + \
            request.form['username'] + "'"
        try:
            cursor.execute(sql)
            number = cursor.rowcount
            if number == 0:
                flash('REGISTER FIRST!')
                return redirect(url_for('login'))
            else:
                row = cursor.fetchone()
                password = row[2]
                if sha256_crypt.verify(request.form['password'], password):
                    session['logged_in'] = True
                    session['user_id'] = row[0]
                    get_transactions()
                    return redirect(url_for('home'))
                else:
                    flash("INCORRECT CREDENTIALS")
                    return render_template('login.html')
        except Exception as e:
            print(e)
            db.rollback()
        db.close()
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        for value in request.form.values():
            if value == "":
                flash('NO FIELD SHOULD BE EMPTY')
                return redirect(url_for('register'))
        password = request.form['password']
        password2 = request.form['password2']
        if password != password2:
            flash("PASSWORDS DON'T MATCH")
            return redirect(url_for('register'))
        db = get_db()
        cursor = db.cursor()
        sql = 'SELECT USERNAME FROM USERS WHERE USERNAME = "' + \
            request.form['username'] + '"'

        try:
            cursor.execute(sql)
            number = cursor.rowcount
            if number != 0:
                flash('ERROR: USERNAME ALREADY EXISTS')
                return redirect(url_for('register'))
        except Exception as e:
            print(e)
            db.rollback()
            db.close()

        hashed = sha256_crypt.encrypt(password)
        sql = "INSERT INTO USERS VALUES(null,'" + request.form['firstname'] + "', '" + \
            request.form['lastname'] + "', '" + \
            request.form['username'] + "', '" + hashed + "', 5000)"
        try:
            cursor.execute(sql)
            db.commit()
        except Exception as e:
            print(e)
            db.rollback()
        db.close()
        flash('Successfully Registered!')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/history')
def history():
    if 'logged_in' in session and not session['logged_in']:
        return redirect(url_for('login'))
    return render_template('history.html', rows=get_transactions(), uid=session['user_id'])


@app.route('/home')
def home():
    if 'logged_in' in session and not session['logged_in']:
        return redirect(url_for('login'))
    db = get_db()
    return render_template('home.html', rows=get_owned_stocks(db), balance=get_balance(db))


@app.route('/buy', methods=['GET', 'POST'])
def buy():
    if 'logged_in' in session and not session['logged_in']:
        return redirect(url_for('login'))
    if request.method == 'POST':
        symbol = request.form['symbol']
        shares = request.form['shares']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db = get_db()
        cursor = db.cursor()
        stock_id, price = get_price(db, symbol, timestamp)
        if stock_id is None or price is None:
            flash('API ERROR - POSSIBLE INVALID STOCK SYMBOL')
            return redirect(url_for('buy'))
        sql = 'SELECT BALANCE FROM USERS WHERE ID = ' + \
            str(session['user_id'])
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
            balance = row[0]
            shares = float(shares)
            price = float(price)
            if balance < shares*price:
                flash('INSUFFICIENT BALANCE')
                return redirect(url_for('buy'))
            else:
                balance -= shares*price
                sql = "UPDATE USERS SET BALANCE = " + \
                    str(balance) + " WHERE ID = " + str(session['user_id'])
                cursor.execute(sql)
                db.commit()
        except Exception as e:
            print(e)
            print('Error in updating balance')
            db.rollback()
        if request.form['type'] == 'market':
            sql = "INSERT INTO TRANSACTIONS VALUES(NULL,'" + str(timestamp) + "'," + str(
                session['user_id']) + ",0," + str(stock_id) + "," + str(shares) + "," + str(price) + ")"
            try:
                cursor.execute(sql)
                db.commit()
            except Exception as e:
                print(e)
                print('Error in inserting into Transactions table')
                db.rollback()
            sql = "SELECT * FROM OWNERSHIP WHERE UID = " + \
                str(session['user_id']) + " AND STOCKID = " + str(stock_id)
            try:
                cursor.execute(sql)
                number = cursor.rowcount
                if number == 0:
                    sql = "INSERT INTO OWNERSHIP VALUES(" + str(
                        session['user_id']) + "," + str(stock_id) + "," + str(shares) + ")"
                    cursor.execute(sql)
                    db.commit()
                else:
                    row = cursor.fetchone()
                    cur_shares = row[2]
                    cur_shares += shares
                    sql = "UPDATE OWNERSHIP SET SHARES = " + \
                        str(cur_shares) + "WHERE STOCKID = " + str(stock_id)
                    cursor.execute(sql)
                    db.commit()
            except Exception as e:
                print('Error in updating Ownership table')
                print(e)
            db.close()
            flash("Successfully Bought!")
            return redirect(url_for('buy'))
        if request.form['type'] == 'user':
            my_price = request.form['price']
            sql = "INSERT INTO OFFERS VALUES(NULL," + str(session['user_id']) + "," + str(
                stock_id) + "," + str(shares) + "," + str(my_price) + ", FALSE)"
            try:
                cursor.execute(sql)
                db.commit()
            except Exception as e:
                print(e)
                print('Error in inserting into Offers table')
                db.rollback()
            db.close()
            flash("Offer Successfully put up!")
            return redirect(url_for('buy'))
    return render_template('buy.html')


@app.route('/sell', methods=['GET', 'POST'])
def sell():
    if 'logged_in' in session and not session['logged_in']:
        return redirect(url_for('login'))
    if request.method == 'POST':
        if 'symbol' not in request.form:
            flash('INVALID STOCK SELECTION')
            return redirect(url_for('sell'))
        symbol = request.form['symbol']
        symbol = symbol.upper()
        shares = request.form['shares']
        if symbol == "" or str(shares) == "":
            flash('NO FIELD SHOULD BE EMPTY')
            return redirect(url_for('sell'))
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db = get_db()
        cursor = db.cursor()
        stock_id, price = get_price(db, symbol, timestamp)
        if stock_id is None or price is None:
            flash('API ERROR - POSSIBLE INVALID STOCK SYMBOL')
            return redirect(url_for('sell'))
        price = float(price)
        shares = float(shares)
        sql = "SELECT * FROM OWNERSHIP WHERE UID = " + \
            str(session['user_id']) + " AND STOCKID = " + str(stock_id)
        try:
            cursor.execute(sql)
            number = cursor.rowcount
            if number == 0:
                flash("INSUFFICIENT SHARES - CAN'T SELL")
                return redirect(url_for('sell'))
            else:
                row = cursor.fetchone()
            if row[2] < shares:
                flash("INSUFFICIENT SHARES - CAN'T SELL")
                return redirect(url_for('sell'))
            else:
                cur_shares = row[2]
                cur_shares -= shares
                sql = "UPDATE OWNERSHIP SET SHARES = " + \
                    str(cur_shares) + " WHERE STOCKID = " + str(stock_id)
                cursor.execute(sql)
                db.commit()
        except Exception as e:
            print('Error in updating Ownership table')
            print(e)
        if request.form['type'] == 'market':
            sql = 'SELECT BALANCE FROM USERS WHERE ID = ' + \
                str(session['user_id'])
            try:
                cursor.execute(sql)
                row = cursor.fetchone()
                balance = row[0]
                shares = float(shares)
                price = float(price)
                balance += shares*price
                sql = "UPDATE USERS SET BALANCE = " + \
                    str(balance) + " WHERE ID = " + str(session['user_id'])
                cursor.execute(sql)
                db.commit()
            except Exception as e:
                print(e)
                print('Error in updating balance')
                db.rollback()
            sql = "INSERT INTO TRANSACTIONS VALUES(NULL,'" + str(timestamp) + "',0," + str(
                session['user_id']) + "," + str(stock_id) + "," + str(shares) + "," + str(price) + ")"
            try:
                cursor.execute(sql)
                db.commit()
            except Exception as e:
                print(e)
                print('Error in inserting into Transactions table')
                db.rollback()
            db.close()
            flash("Successfully Sold!")
            return redirect(url_for('sell'))
        elif request.form['type'] == 'user':
            my_price = request.form['price']
            if str(my_price) == "":
                flash('NO FIELD SHOULD BE EMPTY')
                return redirect(url_for('sell'))
            sql = "INSERT INTO OFFERS VALUES(NULL," + str(session['user_id']) + "," + str(
                stock_id) + "," + str(shares) + "," + str(my_price) + ", TRUE)"
            try:
                cursor.execute(sql)
                db.commit()
            except Exception as e:
                print(e)
                print('Error in inserting into Offers table')
                db.rollback()
            db.close()
            flash("Offer Successfully put up!")
            return redirect(url_for('sell'))
    db = get_db()
    return render_template('sell.html', stocks=get_owned_stocks(db))


@app.route('/offers', methods=['GET', 'POST'])
def offers():
    if request.method == 'POST':
        if 'id' not in request.form:
            flash('PLEASE SELECT AN OFFER TO ACCEPT')
            return redirect(url_for('offers'))
        offer_id = request.form['id']
        sql = "SELECT * FROM OFFERS WHERE ID = " + str(offer_id)
        db = get_db()
        cursor = db.cursor()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
            type = row[5]
            stock_id = row[2]
            shares = row[3]
            price = row[4]
            if type:  # sell offer, so user is buying
                seller_id = row[1]
                sql = 'SELECT BALANCE FROM USERS WHERE ID = ' + \
                    str(session['user_id'])
                try:
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    balance = row[0]
                    shares = float(shares)
                    price = float(price)
                    if balance < shares*price:
                        flash('INSUFFICIENT BALANCE')
                        return redirect(url_for('offers'))
                    else:
                        balance -= shares*price
                        sql = "UPDATE USERS SET BALANCE = " + \
                            str(balance) + " WHERE ID = " + \
                            str(session['user_id'])
                        cursor.execute(sql)
                        db.commit()
                except Exception as e:
                    print(e)
                    print('Error in updating balance')
                    db.rollback()
                sql = "INSERT INTO TRANSACTIONS VALUES(NULL,'" + str(timestamp) + "'," + str(session['user_id']) + "," + str(
                    seller_id) + "," + str(stock_id) + "," + str(shares) + "," + str(price) + ")"
                try:
                    cursor.execute(sql)
                    db.commit()
                except Exception as e:
                    print(e)
                    print('Error in inserting into Transactions table')
                    db.rollback()
                sql = "SELECT * FROM OWNERSHIP WHERE UID = " + \
                    str(session['user_id']) + " AND STOCKID = " + str(stock_id)
                try:
                    cursor.execute(sql)
                    number = cursor.rowcount
                    if number == 0:
                        sql = "INSERT INTO OWNERSHIP VALUES(" + str(
                            session['user_id']) + "," + str(stock_id) + "," + str(shares) + ")"
                        cursor.execute(sql)
                        db.commit()
                    else:
                        row = cursor.fetchone()
                        cur_shares = row[2]
                        cur_shares += shares
                        sql = "UPDATE OWNERSHIP SET SHARES = " + \
                            str(cur_shares) + "WHERE STOCKID = " + str(stock_id)
                        cursor.execute(sql)
                        db.commit()
                except Exception as e:
                    print('Error in updating Ownership table')
                    print(e)
                try:
                    sql = "DELETE FROM OFFERS WHERE ID = " + offer_id
                    cursor.execute(sql)
                    db.commit()
                except Exception as e:
                    print('Error in deleting offer table')
                    print(e)
                db.close()
                flash("Successfully Bought!")
                return redirect(url_for('offers'))

            else:  # offer type is buy, so user is selling
                buyer_id = row[1]
                sql = "SELECT * FROM OWNERSHIP WHERE UID = " + \
                    str(session['user_id']) + " AND STOCKID = " + str(stock_id)
                try:
                    cursor.execute(sql)
                    number = cursor.rowcount
                    if number == 0:
                        flash("INSUFFICIENT SHARES - CAN'T SELL")
                        return redirect(url_for('offers'))
                    else:
                        row = cursor.fetchone()
                    if row[2] < shares:
                        flash("INSUFFICIENT SHARES - CAN'T SELL")
                        return redirect(url_for('offers'))
                    else:
                        cur_shares = row[2]
                        cur_shares -= shares
                        sql = "UPDATE OWNERSHIP SET SHARES = " + \
                            str(cur_shares) + \
                            " WHERE STOCKID = " + str(stock_id)
                        cursor.execute(sql)
                        db.commit()
                except Exception as e:
                    print('Error in updating Ownership table')
                    print(e)
                sql = 'SELECT BALANCE FROM USERS WHERE ID = ' + \
                    str(session['user_id'])
                try:
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    balance = row[0]
                    shares = float(shares)
                    price = float(price)
                    balance += shares*price
                    sql = "UPDATE USERS SET BALANCE = " + \
                        str(balance) + " WHERE ID = " + str(session['user_id'])
                    cursor.execute(sql)
                    db.commit()
                except Exception as e:
                    print(e)
                    print('Error in updating balance')
                    db.rollback()
                    # db.close()
                sql = "INSERT INTO TRANSACTIONS VALUES(NULL,'" + str(timestamp) + "'," + str(buyer_id) + "," + str(
                    session['user_id']) + "," + str(stock_id) + "," + str(shares) + "," + str(price) + ")"
                try:
                    cursor.execute(sql)
                    db.commit()
                except Exception as e:
                    print(e)
                    print('Error in inserting into Transactions table')
                    db.rollback()
                    db.close()
                try:
                    sql = "DELETE FROM OFFERS WHERE ID = " + offer_id
                    cursor.execute(sql)
                    db.commit()
                except Exception as e:
                    print('Error in deleting offer table')
                    print(e)
                db.close()
                flash("Successfully Sold!")
                return redirect(url_for('offers'))

        except Exception as e:
            print('Getting stock id messed up')
            print(e)
            db.rollback()
    return render_template('offers.html', rows=get_offers())


@app.route('/quote', methods=['GET', 'POST'])
def quote():
    if 'logged_in' in session and not session['logged_in']:
        return redirect(url_for('login'))
    price = ""
    if request.method == 'POST':
        symbol = request.form['symbol']
        symbol = symbol.upper()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db = get_db()
        _temp, price = get_price(db, symbol, timestamp)
        if _temp is None or price is None:
            flash('API ERROR - POSSIBLE INVALID STOCK SYMBOL')
            return redirect(url_for('quote'))
    return render_template('quote.html', quoted_price=price)


@app.route('/logout', methods=['GET'])
def logout():
    session['logged_in'] = False
    session['user_id'] = -1
    flash("Logged out")
    return redirect(url_for('login'))


@app.route('/add_funds', methods=['GET', 'POST'])
def add_funds():
    if 'logged_in' in session and not session['logged_in']:
        return redirect(url_for('login'))
    if request.method == 'POST':
        if str(request.form['amount']) == "":
            flash('ENTER AN AMOUNT')
            return redirect(url_for('add_funds'))
        db = get_db()
        cursor = db.cursor()
        sql = 'UPDATE USERS SET BALANCE  = BALANCE + ' + \
            str(request.form['amount']) + \
            ' WHERE ID = ' + str(session['user_id'])
        try:
            cursor.execute(sql)
            db.commit()
            flash('Successfully added funds!')
        except Exception as e:
            print(e)
            db.rollback()
        db.close()
    return render_template('add_funds.html')


def get_transactions():
    db = get_db()
    cursor = db.cursor()
    sql = "SELECT DATETIME, BUYER, SELLER, STOCKID, SHARES, PRCPERSHARE FROM TRANSACTIONS WHERE BUYER = " + \
        str(session['user_id']) + " OR SELLER = " + \
        str(session['user_id']) + " ORDER BY DATETIME DESC"
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        rows_list = []
        for row in rows:
            row = list(row)
            sql = "SELECT SYMBOL FROM STOCKS WHERE ID = " + str(row[3])
            cursor.execute(sql)
            stock_row = cursor.fetchone()
            row[3] = stock_row[0]
            rows_list.append(row)
    except Exception as e:
        print(e)
        db.rollback()
    db.close()
    return rows_list


def get_offers():
    db = get_db()
    cursor = db.cursor()
    sql = "SELECT * FROM OFFERS"
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        rows_list = []
        for row in rows:
            row = list(row)
            sql = "SELECT SYMBOL FROM STOCKS WHERE ID = " + str(row[2])
            cursor.execute(sql)
            stock_row = cursor.fetchone()
            row[2] = stock_row[0]
            rows_list.append(row)
    except Exception as e:
        print(e)
        db.rollback()
    db.close()
    return rows_list


def get_owned_stocks(db):
    cursor = db.cursor()
    sql = 'SELECT STOCKID, SHARES FROM OWNERSHIP WHERE UID = ' + \
        str(session['user_id'])
    stocks_list = []
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        for row in rows:
            stock_id = row[0]
            sql = 'SELECT SYMBOL FROM STOCKS WHERE ID = ' + str(stock_id)
            cursor.execute(sql)
            symbol = cursor.fetchone()
            symbol = symbol[0]
            stocks_list.append((symbol, row[1]))
        return stocks_list
    except Exception as e:
        print(e)
        print('Error in getting balance')
        db.rollback()


def get_db():
    db = pymysql.connect("localhost", "admin", "admin", "stock_trading")
    return db


def get_price(db, symbol, timestamp):
    symbol = symbol.upper()
    API_KEY = 'SY6PUXYPVYZL5E9Z'
    cursor = db.cursor()
    api_required = False
    rowPresent = True
    price_updated = False
    try:
        today = datetime.now().date()
        sql = "SELECT PRICE, DATETIME FROM STOCKS WHERE SYMBOL = '" + \
            str(symbol) + "'"
        cursor.execute(sql)
        number = cursor.rowcount
        if number == 0:
            api_required = True
            rowPresent = False
        else:
            row = cursor.fetchone()
            price = row[0]
            day = row[1].date()
            if day != today:
                api_required = True
    except Exception as e:
        print(e)
        print('Error in api requirement checking')
        db.rollback()
    if api_required:
        try:
            r = requests.get(
                'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=' + symbol + '&apikey=' + API_KEY)
            if (r.status_code == 200):
                result = r.json()
                dataForAllDays = result['Time Series (Daily)']
                dataForSingleDate = dataForAllDays[(
                    datetime.now() - timedelta(1)).strftime('%Y-%m-%d')]
                price = dataForSingleDate['4. close']
                price_updated = True
        except Exception as e:
            print(e)
            return None, None
    if not rowPresent:
        try:
            sql = "INSERT INTO STOCKS VALUES(null,'" + symbol + \
                "'," + str(price) + ",'" + str(timestamp) + "')"
            cursor.execute(sql)
            db.commit()
            sql = "SELECT ID FROM STOCKS WHERE SYMBOL = '" + symbol + "'"
            cursor.execute(sql)
            row = cursor.fetchone()
            stock_id = row[0]
        except Exception as e:
            print(e)
            print('Insertion of new value fucked up')
            db.rollback()
    else:
        sql = "SELECT ID FROM STOCKS WHERE SYMBOL = '" + symbol + "'"
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
            stock_id = row[0]
            if price_updated:
                sql = "UPDATE STOCKS SET PRICE = " + \
                    str(price) + " WHERE ID = " + str(stock_id)
                cursor.execute(sql)
                db.commit()
                sql = "UPDATE STOCKS SET DATETIME = '" + \
                    str(timestamp) + "' WHERE ID = " + str(stock_id)
                cursor.execute(sql)
                db.commit()
        except Exception as e:
            print(e)
            print('Error in updating the stock price')
            db.rollback()
    return stock_id, price


def get_balance(db):
    cursor = db.cursor()
    sql = 'SELECT BALANCE FROM USERS WHERE ID = ' + str(session['user_id'])
    try:
        cursor.execute(sql)
        row = cursor.fetchone()
        balance = row[0]
        return balance
    except Exception as e:
        print(e)
        print('Error in getting balance')
        db.rollback()


if __name__ == '__main__':
    app.config.from_object(__name__)
    app.config.update(dict(SECRET_KEY='development key',))
    app.run(debug=True)
