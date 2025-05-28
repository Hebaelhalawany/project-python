import psycopg2
from psycopg2 import sql, errors
from datetime import datetime
import getpass
import bcrypt
import sys

class DatabaseConnection:
    _instance = None
    
    def __new__(cls, dbname, user, password, host="localhost", port="5432"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            try:
                cls._instance.connection = psycopg2.connect(
                    dbname=dbname,
                    user=user,
                    password=password,
                    host=host,
                    port=port
                )
                cls._instance.connection.autocommit = True
            except psycopg2.OperationalError as e:
                print(f"Failed to connect to database: {e}")
                raise
        return cls._instance
    
    def get_cursor(self):
        return self.connection.cursor()
    
    def close(self):
        if self.connection:
            self.connection.close()
            DatabaseConnection._instance = None

class User:
    def __init__(self, user_id, username, password_hash, is_admin=False, created_at=None):
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.created_at = created_at
    
    @classmethod
    def create(cls, username, password, is_admin=False):
        """Hash password and create new user"""
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return cls(None, username, password_hash, is_admin)
    
    def verify_password(self, password):
        """Verify password against stored hash"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def save(self, db):
        """Save user to database"""
        with db.get_cursor() as cursor:
            if self.user_id is None:
                query = sql.SQL("""
                    INSERT INTO users (username, password_hash, is_admin)
                    VALUES (%s, %s, %s)
                    RETURNING user_id
                """)
                cursor.execute(query, (self.username, self.password_hash, self.is_admin))
                self.user_id = cursor.fetchone()[0]
            else:
                query = sql.SQL("""
                    UPDATE users
                    SET username = %s, password_hash = %s, is_admin = %s
                    WHERE user_id = %s
                """)
                cursor.execute(query, (self.username, self.password_hash, self.is_admin, self.user_id))
    
    @classmethod
    def get_by_username(cls, db, username):
        """Retrieve user by username"""
        with db.get_cursor() as cursor:
            query = sql.SQL("SELECT * FROM users WHERE username = %s")
            cursor.execute(query, (username,))
            result = cursor.fetchone()
            if result:
                return cls(*result)
        return None
    
    @classmethod
    def get_by_id(cls, db, user_id):
        """Retrieve user by ID"""
        with db.get_cursor() as cursor:
            query = sql.SQL("SELECT * FROM users WHERE user_id = %s")
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            if result:
                return cls(*result)
        return None

class Loan:
    def __init__(self, loan_id, user_id, amount, term, interest_rate, status, created_at, current_balance):
        self.loan_id = loan_id
        self.user_id = user_id
        self.amount = float(amount)
        self.term = int(term)
        self.interest_rate = float(interest_rate)
        self.status = status  # 'pending', 'approved', 'rejected', 'paid'
        self.created_at = created_at
        self.current_balance = float(current_balance)
    
    def save(self, db):
        """Save loan to database"""
        with db.get_cursor() as cursor:
            if self.loan_id is None:
                query = sql.SQL("""
                    INSERT INTO loans (user_id, amount, term, interest_rate, status, created_at, current_balance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING loan_id
                """)
                cursor.execute(query, (
                    self.user_id, self.amount, self.term, 
                    self.interest_rate, self.status, 
                    self.created_at, self.current_balance
                ))
                self.loan_id = cursor.fetchone()[0]
            else:
                query = sql.SQL("""
                    UPDATE loans
                    SET user_id = %s, amount = %s, term = %s, interest_rate = %s, 
                        status = %s, created_at = %s, current_balance = %s
                    WHERE loan_id = %s
                """)
                cursor.execute(query, (
                    self.user_id, self.amount, self.term, 
                    self.interest_rate, self.status, 
                    self.created_at, self.current_balance,
                    self.loan_id
                ))
    
    @classmethod
    def get_by_id(cls, db, loan_id):
        """Retrieve loan by ID"""
        with db.get_cursor() as cursor:
            query = sql.SQL("SELECT * FROM loans WHERE loan_id = %s")
            cursor.execute(query, (loan_id,))
            result = cursor.fetchone()
            if result:
                return cls(*result)
        return None
    
    @classmethod
    def get_user_loans(cls, db, user_id):
        """Retrieve all loans for a user"""
        with db.get_cursor() as cursor:
            query = sql.SQL("SELECT * FROM loans WHERE user_id = %s ORDER BY created_at DESC")
            cursor.execute(query, (user_id,))
            return [cls(*row) for row in cursor.fetchall()]
    
    def make_payment(self, db, amount):
        """Process a payment against the loan"""
        if amount <= 0:
            return False, "Payment amount must be positive"
        
        if amount > self.current_balance:
            return False, "Payment exceeds current balance"
        
        self.current_balance -= amount
        self.save(db)
        

        Payment.create(db, self.loan_id, amount).save(db)
        
        if self.current_balance == 0:
            self.status = 'paid'
            self.save(db)
        
        return True, "Payment successful"

class Payment:
    def __init__(self, payment_id, loan_id, amount, payment_date):
        self.payment_id = payment_id
        self.loan_id = loan_id
        self.amount = float(amount)
        self.payment_date = payment_date
    
    @classmethod
    def create(cls, db, loan_id, amount):
        """Create a new payment record"""
        return cls(None, loan_id, amount, datetime.now())
    
    def save(self, db):
        """Save payment to database"""
        with db.get_cursor() as cursor:
            if self.payment_id is None:
                query = sql.SQL("""
                    INSERT INTO payments (loan_id, amount, payment_date)
                    VALUES (%s, %s, %s)
                    RETURNING payment_id
                """)
                cursor.execute(query, (self.loan_id, self.amount, self.payment_date))
                self.payment_id = cursor.fetchone()[0]
            else:
                query = sql.SQL("""
                    UPDATE payments
                    SET loan_id = %s, amount = %s, payment_date = %s
                    WHERE payment_id = %s
                """)
                cursor.execute(query, (self.loan_id, self.amount, self.payment_date, self.payment_id))
    
    @classmethod
    def get_loan_payments(cls, db, loan_id):
        """Retrieve all payments for a loan"""
        with db.get_cursor() as cursor:
            query = sql.SQL("SELECT * FROM payments WHERE loan_id = %s ORDER BY payment_date DESC")
            cursor.execute(query, (loan_id,))
            return [cls(*row) for row in cursor.fetchall()]

class LoanApplicationSystem:
    def __init__(self, db_config):
        self.db = DatabaseConnection(**db_config)
        self.current_user = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Create tables if they don't exist"""
        try:
            with self.db.get_cursor() as cursor:

                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'users'
                    )
                """)
                if not cursor.fetchone()[0]:

                    cursor.execute("""
                        CREATE TABLE users (
                            user_id SERIAL PRIMARY KEY,
                            username VARCHAR(50) UNIQUE NOT NULL,
                            password_hash VARCHAR(100) NOT NULL,
                            is_admin BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    

                    cursor.execute("""
                        CREATE TABLE loans (
                            loan_id SERIAL PRIMARY KEY,
                            user_id INTEGER REFERENCES users(user_id),
                            amount DECIMAL(10, 2) NOT NULL,
                            term INTEGER NOT NULL,
                            interest_rate DECIMAL(5, 2) NOT NULL,
                            status VARCHAR(20) DEFAULT 'pending',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            current_balance DECIMAL(10, 2) NOT NULL
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE TABLE payments (
                            payment_id SERIAL PRIMARY KEY,
                            loan_id INTEGER REFERENCES loans(loan_id),
                            amount DECIMAL(10, 2) NOT NULL,
                            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    admin = User.create("admin", "admin123", True)
                    admin.save(self.db)
                    print("Database initialized with admin user (username: admin, password: admin123)")
                    
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise
    
    def login(self):
        print("\n=== Login ===")
        username = input("Username: ")
        password = getpass.getpass("Password: ")
        
        user = User.get_by_username(self.db, username)
        if user and user.verify_password(password):
            self.current_user = user
            print(f"\nWelcome, {user.username}!")
            return True
        else:
            print("\nInvalid username or password.")
            return False
    
    def register(self):
        print("\n=== Register ===")
        username = input("Username: ")
        if User.get_by_username(self.db, username):
            print("Username already exists.")
            return False
        
        password = getpass.getpass("Password: ")
        confirm_password = getpass.getpass("Confirm Password: ")
        
        if password != confirm_password:
            print("Passwords do not match.")
            return False
        
        user = User.create(username, password)
        user.save(self.db)
        print("\nRegistration successful! Please login.")
        return True
    
    def apply_for_loan(self):
        if not self.current_user:
            print("Please login first.")
            return
        
        print("\n=== Apply for Loan ===")
        try:
            amount = float(input("Loan amount: "))
            term = int(input("Loan term (in months): "))
            interest_rate = min(5.0 + (term / 12), 15.0)
            
            loan = Loan(
                None, self.current_user.user_id, amount, term, 
                interest_rate, 'pending', datetime.now(), amount
            )
            loan.save(self.db)
            
            print(f"\nLoan application submitted successfully!")
            print(f"Amount: ${amount:.2f}")
            print(f"Term: {term} months")
            print(f"Interest Rate: {interest_rate:.2f}%")
        except ValueError:
            print("Invalid input. Please enter numbers only.")
    
    def make_payment(self):
        if not self.current_user:
            print("Please login first.")
            return
        
        loans = Loan.get_user_loans(self.db, self.current_user.user_id)
        if not loans:
            print("You have no active loans.")
            return
        
        print("\n=== Your Loans ===")
        for i, loan in enumerate(loans, 1):
            print(f"{i}. Loan ID: {loan.loan_id} | Amount: ${loan.amount:.2f} | Balance: ${loan.current_balance:.2f} | Status: {loan.status}")
        
        try:
            choice = int(input("\nSelect loan to pay (number): ")) - 1
            if 0 <= choice < len(loans):
                loan = loans[choice]
                if loan.status != 'approved':
                    print("This loan is not approved for payment.")
                    return
                
                amount = float(input("Payment amount: "))
                success, message = loan.make_payment(self.db, amount)
                print(message)
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    def check_balance(self):
        if not self.current_user:
            print("Please login first.")
            return
        
        loans = Loan.get_user_loans(self.db, self.current_user.user_id)
        if not loans:
            print("You have no active loans.")
            return
        
        print("\n=== Your Loan Balances ===")
        for loan in loans:
            print(f"Loan ID: {loan.loan_id} | Original Amount: ${loan.amount:.2f} | Current Balance: ${loan.current_balance:.2f} | Status: {loan.status}")
    
    def view_payment_history(self):
        if not self.current_user:
            print("Please login first.")
            return
        
        loans = Loan.get_user_loans(self.db, self.current_user.user_id)
        if not loans:
            print("You have no active loans.")
            return
        
        print("\n=== Your Loans ===")
        for i, loan in enumerate(loans, 1):
            print(f"{i}. Loan ID: {loan.loan_id} | Amount: ${loan.amount:.2f} | Balance: ${loan.current_balance:.2f}")
        
        try:
            choice = int(input("\nSelect loan to view payment history (number): ")) - 1
            if 0 <= choice < len(loans):
                loan = loans[choice]
                payments = Payment.get_loan_payments(self.db, loan.loan_id)
                
                if not payments:
                    print("No payments found for this loan.")
                    return
                
                print(f"\n=== Payment History for Loan {loan.loan_id} ===")
                for payment in payments:
                    print(f"Date: {payment.payment_date} | Amount: ${payment.amount:.2f}")
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    def admin_menu(self):
        while True:
            print("\n=== Admin Menu ===")
            print("1. Approve/Reject Loans")
            print("2. View All Loans")
            print("3. Back to Main Menu")
            
            choice = input("Enter your choice: ")
            
            if choice == '1':
                self.approve_loans()
            elif choice == '2':
                self.view_all_loans()
            elif choice == '3':
                break
            else:
                print("Invalid choice. Please try again.")
    
    def approve_loans(self):
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT l.*, u.username 
                FROM loans l
                JOIN users u ON l.user_id = u.user_id
                WHERE l.status = 'pending'
            """)
            pending_loans = cursor.fetchall()
        
        if not pending_loans:
            print("No pending loans to approve.")
            return
        
        print("\n=== Pending Loans ===")
        for i, loan in enumerate(pending_loans, 1):
            print(f"{i}. Loan ID: {loan[0]} | User: {loan[8]} | Amount: ${loan[2]:.2f} | Term: {loan[3]} months")
        
        try:
            choice = int(input("\nSelect loan to approve/reject (number): ")) - 1
            if 0 <= choice < len(pending_loans):
                loan_id = pending_loans[choice][0]
                action = input("Approve (A) or Reject (R)? ").lower()
                
                if action == 'a':
                    status = 'approved'
                    message = "Loan approved successfully."
                elif action == 'r':
                    status = 'rejected'
                    message = "Loan rejected."
                else:
                    print("Invalid action.")
                    return
                
                with self.db.get_cursor() as cursor:
                    cursor.execute("""
                        UPDATE loans
                        SET status = %s
                        WHERE loan_id = %s
                    """, (status, loan_id))
                print(message)
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    def view_all_loans(self):
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT l.*, u.username 
                FROM loans l
                JOIN users u ON l.user_id = u.user_id
                ORDER BY l.created_at DESC
            """)
            all_loans = cursor.fetchall()
        
        if not all_loans:
            print("No loans found.")
            return
        
        print("\n=== All Loans ===")
        for loan in all_loans:
            print(f"Loan ID: {loan[0]} | User: {loan[8]} | Amount: ${loan[2]:.2f} | Term: {loan[3]} months | Status: {loan[5]}")
    
    def run(self):
        print("=== Loan Application System ===")
        
        while True:
            if not self.current_user:
                print("\n1. Login")
                print("2. Register")
                print("3. Exit")
                
                choice = input("Enter your choice: ")
                
                if choice == '1':
                    if self.login():
                        continue
                elif choice == '2':
                    self.register()
                elif choice == '3':
                    print("Goodbye!")
                    break
                else:
                    print("Invalid choice. Please try again.")
            else:
                if self.current_user.is_admin:
                    print("\n=== Main Menu (Admin) ===")
                    print("1. Apply for Loan")
                    print("2. Make a Payment") 
                    print("3. Check Balance")
                    print("4. View Payment History")
                    print("5. Admin Functions")
                    print("6. Logout")
                    
                    choice = input("Enter your choice: ")
                    
                    if choice == '1':
                        self.apply_for_loan()
                    elif choice == '2':
                        self.make_payment()
                    elif choice == '3':
                        self.check_balance()
                    elif choice == '4':
                        self.view_payment_history()
                    elif choice == '5':
                        self.admin_menu()
                    elif choice == '6':
                        self.current_user = None
                        print("Logged out successfully.")
                    else:
                        print("Invalid choice. Please try again.")
                else:
                    print("\n=== Main Menu ===")
                    print("1. Apply for Loan")
                    print("2. Make a Payment")
                    print("3. Check Balance")
                    print("4. View Payment History")
                    print("5. Logout")
                    
                    choice = input("Enter your choice: ")
                    
                    if choice == '1':
                        self.apply_for_loan()
                    elif choice == '2':
                        self.make_payment()
                    elif choice == '3':
                        self.check_balance()
                    elif choice == '4':
                        self.view_payment_history()
                    elif choice == '5':
                        self.current_user = None
                        print("Logged out successfully.")
                    else:
                        print("Invalid choice. Please try again.")

def get_database_config():
    """Get database configuration from user input"""
    print("=== Database Configuration ===")
    print("Please provide your PostgreSQL connection details:")
    
    host = input("Host (default: localhost): ").strip() or "localhost"
    port = input("Port (default: 5432): ").strip() or "5432"
    dbname = input("Database name (default: loan_system): ").strip() or "loan_system"
    user = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    
    return {
        'dbname': dbname,
        'user': user,
        'password': password,
        'host': host,
        'port': port
    }

def test_connection(db_config):
    """Test database connection"""
    try:
        conn = psycopg2.connect(**db_config)
        conn.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

def create_database_if_not_exists(admin_config, db_name):
    """Create database if it doesn't exist"""
    try:
        conn = psycopg2.connect(**admin_config)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cursor.fetchone():
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"Created database '{db_name}'")
        else:
            print(f"Database '{db_name}' already exists")
            
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Failed to create database: {e}")
        return False

if __name__ == "__main__":
    print("=== PostgreSQL Loan Application System ===\n")
    db_config = get_database_config()
    
    if not test_connection(db_config):
        print("\nFailed to connect to database. Please check your credentials and try again.")
        sys.exit(1)
    
    try:
        test_conn = psycopg2.connect(**db_config)
        test_conn.close()
    except psycopg2.OperationalError as e:
        if "does not exist" in str(e):
            print(f"\nDatabase '{db_config['dbname']}' doesn't exist. Attempting to create it...")
            
            admin_config = db_config.copy()
            admin_config['dbname'] = 'postgres'
            
            if not create_database_if_not_exists(admin_config, db_config['dbname']):
                print("Failed to create database. Please create it manually or use an existing database.")
                sys.exit(1)
        else:
            print(f"Database connection error: {e}")
            sys.exit(1)
    
    try:
        system = LoanApplicationSystem(db_config)
        system.run()
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'system' in locals():
            system.db.close()