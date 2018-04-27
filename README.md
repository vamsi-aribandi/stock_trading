# Stock Trading
A website which simulates a simple stock market

Features:
* Users can Buy/Sell at market price (stock prices are realtime)
* Users can Post/Accept offers to buy/sell a certain number of stocks at a certain price
* Users can view their owned stocks as well as their transaction history
* Passwords are encrypted with sha256

## Test it
To host the project locally, set up the required MySQL database specified in schemas.txt and run app.py with the python 3.x interpreter
```
python3 app.py
```
Flask, pymysql, MySQL and Alpha Vantage must be installed.

## Built with
* [flask](http://flask.pocoo.org/) - The (python3) web framework used
* [Bootstrap](https://getbootstrap.com/) - The HTML/CSS library used
* [Alpha Vantage](https://www.alphavantage.co/) - The python library used to get realtime prices of stocks
* [MySQL](https://www.mysql.com/) - DBMS used
* [pymysql](https://pymysql.readthedocs.io/en/latest/) - The python library used to interface with MySQL
