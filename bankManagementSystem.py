

import os
import sys
import random
import string
import bcrypt
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///bank.db")

engine = create_engine(DATABASE_URL)

Base = declarative_base()

Session = sessionmaker(bind=engine)


class User(Base):

    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default='user')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    accounts = relationship("Account", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}', active={self.is_active})>"


class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    account_number = Column(String, unique=True, nullable=False)
    account_type = Column(String, default='savings')
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")

    def __repr__(self):
        return f"<Account(id={self.id}, number='{self.account_number}', type='{self.account_type}', balance={self.balance:.2f})>"


class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'))
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.now)
    target_account_number = Column(String, nullable=True)

    account = relationship("Account", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, type='{self.type}', amount={self.amount:.2f}, timestamp='{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}')>"


def init_db():

    print("Attempting to create/check database tables...")
    try:
        Base.metadata.create_all(engine)
        print("Database tables created/checked successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")



class AuthManager:

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

    def register_user(self, username: str, password: str, role: str = 'user') -> tuple[bool, str]:
        session = Session()
        try:
            if session.query(User).filter_by(username=username).first():
                return False, "Username already exists. Please choose a different one."

            hashed_password = self.hash_password(password)
            new_user = User(username=username, password_hash=hashed_password, role=role)
            session.add(new_user)
            session.commit()
            return True, "Registration successful. You can now log in."
        except SQLAlchemyError as e:
            session.rollback()
            return False, f"Registration failed due to a database error: {e}"
        except Exception as e:
            session.rollback()
            return False, f"An unexpected error occurred during registration: {e}"
        finally:
            session.close()

    def login_user(self, username: str, password: str) -> tuple[User | None, str]:
        session = Session()
        try:
            user = session.query(User).filter_by(username=username, is_active=True).first()
            if user and self.check_password(password, user.password_hash):
                return user, "Login successful."
            elif user and not user.is_active:
                return None, "Your account is currently inactive. Please contact administration."
            else:
                return None, "Invalid username or password."
        except SQLAlchemyError as e:
            return None, f"Login failed due to a database error: {e}"
        except Exception as e:
            return None, f"An unexpected error occurred during login: {e}"
        finally:
            session.close()


current_user = None



class BankOperations:

    def generate_account_number(self) -> str:
        return ''.join(random.choices(string.digits, k=10))

    def create_account(self, user_id: int, account_type: str = 'savings') -> tuple[bool, str]:
        session = Session()
        try:
            user = session.get(User, user_id)
            if not user:
                return False, "User not found."

            account_number = self.generate_account_number()
            while session.query(Account).filter_by(account_number=account_number).first():
                account_number = self.generate_account_number()

            new_account = Account(user_id=user_id, account_number=account_number,
                                  account_type=account_type, balance=0.0)
            session.add(new_account)
            session.commit()
            return True, f"Account '{account_number}' of type '{account_type}' created successfully for {user.username}."
        except SQLAlchemyError as e:
            session.rollback()
            return False, f"Failed to create account due to a database error: {e}"
        except Exception as e:
            session.rollback()
            return False, f"An unexpected error occurred during account creation: {e}"
        finally:
            session.close()

    def deposit(self, account_number: str, amount: float, description: str = "Deposit") -> tuple[bool, str]:
        if amount <= 0:
            return False, "Deposit amount must be a positive number."
        session = Session()
        try:
            account = session.query(Account).filter_by(account_number=account_number).first()
            if not account:
                return False, "Account not found."

            account.balance += amount
            transaction = Transaction(account_id=account.id, type='deposit', amount=amount, description=description)
            session.add(transaction)
            session.commit()
            return True, f"Deposited {amount:.2f} into account {account_number}. New balance: {account.balance:.2f}"
        except SQLAlchemyError as e:
            session.rollback()
            return False, f"Deposit failed due to a database error: {e}"
        except Exception as e:
            session.rollback()
            return False, f"An unexpected error occurred during deposit: {e}"
        finally:
            session.close()

    def withdraw(self, account_number: str, amount: float, description: str = "Withdrawal") -> tuple[bool, str]:
        if amount <= 0:
            return False, "Withdrawal amount must be a positive number."
        session = Session()
        try:
            account = session.query(Account).filter_by(account_number=account_number).first()
            if not account:
                return False, "Account not found."
            if account.balance < amount:
                return False, "Insufficient balance. Available: {account.balance:.2f}"

            account.balance -= amount
            transaction = Transaction(account_id=account.id, type='withdrawal', amount=amount, description=description)
            session.add(transaction)
            session.commit()
            return True, f"Withdrew {amount:.2f} from account {account_number}. New balance: {account.balance:.2f}"
        except SQLAlchemyError as e:
            session.rollback()
            return False, f"Withdrawal failed due to a database error: {e}"
        except Exception as e:
            session.rollback()
            return False, f"An unexpected error occurred during withdrawal: {e}"
        finally:
            session.close()

    def transfer(self, source_account_number: str, target_account_number: str, amount: float,
                 description: str = "Transfer") -> tuple[bool, str]:
        if amount <= 0:
            return False, "Transfer amount must be a positive number."
        if source_account_number == target_account_number:
            return False, "Cannot transfer money to the same account."

        session = Session()
        try:
            source_account = session.query(Account).filter_by(account_number=source_account_number).first()
            target_account = session.query(Account).filter_by(account_number=target_account_number).first()

            if not source_account:
                return False, "Source account not found."
            if not target_account:
                return False, "Target account not found."
            if source_account.balance < amount:
                return False, f"Insufficient balance in source account {source_account_number}. Available: {source_account.balance:.2f}"

            source_account.balance -= amount
            target_account.balance += amount

            transfer_out_txn = Transaction(
                account_id=source_account.id,
                type='transfer_out',
                amount=amount,
                description=f"Transfer to {target_account_number} ({description})",
                target_account_number=target_account_number
            )
            transfer_in_txn = Transaction(
                account_id=target_account.id,
                type='transfer_in',
                amount=amount,
                description=f"Transfer from {source_account_number} ({description})",
                target_account_number=source_account_number
            )
            session.add_all([transfer_out_txn, transfer_in_txn])
            session.commit()
            return True, (f"Transferred {amount:.2f} from {source_account_number} to {target_account_number}. "
                          f"Source balance: {source_account.balance:.2f}, Target balance: {target_account.balance:.2f}")
        except SQLAlchemyError as e:
            session.rollback()
            return False, f"Transfer failed due to a database error: {e}"
        except Exception as e:
            session.rollback()
            return False, f"An unexpected error occurred during transfer: {e}"
        finally:
            session.close()

    def get_account_balance(self, account_number: str) -> tuple[float | None, bool]:
        session = Session()
        try:
            account = session.query(Account).filter_by(account_number=account_number).first()
            if account:
                return account.balance, True
            return None, False  # Account not found
        except SQLAlchemyError as e:
            print(f"Error retrieving balance: {e}")
            return None, False
        finally:
            session.close()

    def get_transaction_history(self, account_number: str) -> tuple[list[Transaction] | None, str]:
        session = Session()
        try:
            account = session.query(Account).filter_by(account_number=account_number).first()
            if not account:
                return None, "Account not found."

            transactions = session.query(Transaction).filter_by(account_id=account.id).order_by(
                Transaction.timestamp.desc()).all()
            return transactions, "Success"
        except SQLAlchemyError as e:
            return None, f"Failed to retrieve transaction history due to a database error: {e}"
        except Exception as e:
            return None, f"An unexpected error occurred while fetching transaction history: {e}"
        finally:
            session.close()

    def get_user_accounts(self, user_id: int) -> tuple[list[Account], str]:
        session = Session()
        try:
            accounts = session.query(Account).filter_by(user_id=user_id).all()
            return accounts, "Success"
        except SQLAlchemyError as e:
            return [], f"Failed to retrieve user accounts due to a database error: {e}"
        except Exception as e:
            return [], f"An unexpected error occurred while fetching user accounts: {e}"
        finally:
            session.close()


class AdminOperations:
    def get_all_users(self) -> tuple[list[User], str]:
        session = Session()
        try:
            users = session.query(User).all()
            return users, "Success"
        except SQLAlchemyError as e:
            return [], f"Failed to retrieve users due to a database error: {e}"
        except Exception as e:
            return [], f"An unexpected error occurred while fetching all users: {e}"
        finally:
            session.close()

    def get_all_accounts(self) -> tuple[list[Account], str]:
        session = Session()
        try:
            accounts = session.query(Account).all()
            return accounts, "Success"
        except SQLAlchemyError as e:
            return [], f"Failed to retrieve accounts due to a database error: {e}"
        except Exception as e:
            return [], f"An unexpected error occurred while fetching all accounts: {e}"
        finally:
            session.close()

    def toggle_user_status(self, user_id: int) -> tuple[bool, str]:
        session = Session()
        try:
            user = session.get(User, user_id)
            if not user:
                return False, f"User with ID {user_id} not found."

            user.is_active = not user.is_active
            session.commit()
            status_text = "activated" if user.is_active else "deactivated"
            return True, f"User '{user.username}' (ID: {user.id}) has been {status_text} successfully."
        except SQLAlchemyError as e:
            session.rollback()
            return False, f"Failed to toggle user status due to a database error: {e}"
        except Exception as e:
            session.rollback()
            return False, f"An unexpected error occurred while toggling user status: {e}"
        finally:
            session.close()

    def search_user_by_username(self, username_query: str) -> tuple[list[User], str]:
        session = Session()
        try:
            users = session.query(User).filter(User.username.ilike(f"%{username_query}%")).all()
            return users, "Success"
        except SQLAlchemyError as e:
            return [], f"Failed to search user due to a database error: {e}"
        except Exception as e:
            return [], f"An unexpected error occurred during user search: {e}"
        finally:
            session.close()

    def get_all_transactions(self) -> tuple[list[Transaction], str]:
        session = Session()
        try:
            transactions = session.query(Transaction).order_by(Transaction.timestamp.desc()).all()
            return transactions, "Success"
        except SQLAlchemyError as e:
            return [], f"Failed to retrieve all transactions due to a database error: {e}"
        except Exception as e:
            return [], f"An unexpected error occurred while fetching all transactions: {e}"
        finally:
            session.close()


init_db()
auth_manager = AuthManager()
bank_ops = BankOperations()
admin_ops = AdminOperations()



def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def main_menu() -> str:
    clear_screen()
    print("\n--- Bank Management System ---")
    print("1. Register New Account")
    print("2. Login")
    print("3. Exit")
    choice = input("Enter your choice: ").strip()
    return choice


def user_menu() -> str:
    clear_screen()
    user_info = f"Welcome, {current_user.username} ({current_user.role})!" if current_user else "Welcome!"
    print(f"\n--- {user_info} ---")
    print("1. View My Accounts")
    print("2. Create New Bank Account")
    print("3. Deposit Funds")
    print("4. Withdraw Funds")
    print("5. Transfer Funds")
    print("6. View Account Transaction History")
    print("7. Logout")
    choice = input("Enter your choice: ").strip()
    return choice


def admin_menu() -> str:
    clear_screen()
    user_info = f"Admin Dashboard ({current_user.username})" if current_user else "Admin Dashboard"
    print(f"\n--- {user_info} ---")
    print("1. View All System Users")
    print("2. Toggle User Active Status")
    print("3. View All Bank Accounts")
    print("4. View All System Transactions")
    print("5. Search User by Username")
    print("6. Logout")
    choice = input("Enter your choice: ").strip()
    return choice


def handle_registration():
    print("\n--- New User Registration ---")
    username = input("Enter new username: ").strip()
    password = input("Enter password: ").strip()
    if not username or not password:
        print("Username and password cannot be empty.")
        input("Press Enter to continue...")
        return
    success, message = auth_manager.register_user(username, password)
    print(message)
    input("Press Enter to continue...")


def handle_login():
    global current_user
    print("\n--- User Login ---")
    username = input("Enter username: ").strip()
    password = input("Enter password: ").strip()
    user, message = auth_manager.login_user(username, password)
    if user:
        current_user = user
        print(message)
    else:
        current_user = None
        print(message)
    input("Press Enter to continue...")


def handle_view_accounts():
    if not current_user:
        print("Error: You must be logged in to view accounts.")
        input("Press Enter to continue...")
        return

    accounts, msg = bank_ops.get_user_accounts(current_user.id)
    if accounts:
        print(f"\n--- Accounts for {current_user.username} ---")
        for i, acc in enumerate(accounts):
            print(
                f"  {i + 1}. Account No: {acc.account_number}, Type: {acc.account_type.capitalize()}, Balance: {acc.balance:.2f}")
    else:
        print(f"No bank accounts found for {current_user.username}.")
    print(msg)
    input("Press Enter to continue...")


def handle_create_account():
    if not current_user:
        print("Error: You must be logged in to create an account.")
        input("Press Enter to continue...")
        return

    print("\n--- Create New Bank Account ---")
    acc_type = input("Enter account type (e.g., savings, checking): ").strip().lower()
    if not acc_type:
        print("Account type cannot be empty.")
        input("Press Enter to continue...")
        return

    success, message = bank_ops.create_account(current_user.id, acc_type)
    print(message)
    input("Press Enter to continue...")


def handle_deposit():
    if not current_user:
        print("Error: You must be logged in to deposit funds.")
        input("Press Enter to continue...")
        return

    print("\n--- Deposit Funds ---")
    account_num = input("Enter the account number to deposit into: ").strip()
    try:
        amount = float(input("Enter amount to deposit: "))
        success, message = bank_ops.deposit(account_num, amount)
        print(message)
    except ValueError:
        print("Invalid amount. Please enter a numerical value.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    input("Press Enter to continue...")


def handle_withdraw():
    if not current_user:
        print("Error: You must be logged in to withdraw funds.")
        input("Press Enter to continue...")
        return

    print("\n--- Withdraw Funds ---")
    account_num = input("Enter the account number to withdraw from: ").strip()
    try:
        amount = float(input("Enter amount to withdraw: "))
        success, message = bank_ops.withdraw(account_num, amount)
        print(message)
    except ValueError:
        print("Invalid amount. Please enter a numerical value.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    input("Press Enter to continue...")


def handle_transfer():
    if not current_user:
        print("Error: You must be logged in to transfer funds.")
        input("Press Enter to continue...")
        return

    print("\n--- Transfer Funds ---")
    source_acc = input("Enter your source account number: ").strip()
    target_acc = input("Enter target account number: ").strip()
    try:
        amount = float(input("Enter amount to transfer: "))
        success, message = bank_ops.transfer(source_acc, target_acc, amount)
        print(message)
    except ValueError:
        print("Invalid amount. Please enter a numerical value.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    input("Press Enter to continue...")


def handle_transaction_history():
    if not current_user:
        print("Error: You must be logged in to view transaction history.")
        input("Press Enter to continue...")
        return

    print("\n--- Account Transaction History ---")
    account_num = input("Enter account number to view history: ").strip()
    transactions, msg = bank_ops.get_transaction_history(account_num)
    if transactions:
        print(f"\n--- History for Account {account_num} ---")
        for txn in transactions:
            description_display = txn.description if txn.description else 'N/A'
            print(f"[{txn.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] "
                  f"Type: {txn.type:<12} Amount: {txn.amount:9.2f} "
                  f"Desc: {description_display[:30].ljust(30)}")  # Truncate and pad description
    else:
        print(f"No transactions found for account {account_num}.")
    print(msg)
    input("Press Enter to continue...")


def handle_admin_view_users():
    if not current_user or current_user.role != 'admin':
        print("Access Denied: Only administrators can view all users.")
        input("Press Enter to continue...")
        return

    users, msg = admin_ops.get_all_users()
    if users:
        print("\n--- All System Users ---")
        for user in users:
            print(f"ID: {user.id}, Username: {user.username:<15}, Role: {user.role:<8}, Active: {user.is_active}")
    else:
        print("No users found in the system.")
    print(msg)
    input("Press Enter to continue...")


def handle_admin_toggle_user_status():
    if not current_user or current_user.role != 'admin':
        print("Access Denied: Only administrators can toggle user status.")
        input("Press Enter to continue...")
        return

    print("\n--- Toggle User Active Status ---")
    try:
        user_id_str = input("Enter the User ID to toggle status (e.g., 1): ").strip()
        user_id = int(user_id_str)
        success, message = admin_ops.toggle_user_status(user_id)
        print(message)
    except ValueError:
        print("Invalid input. Please enter a numerical User ID.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    input("Press Enter to continue...")


def handle_admin_view_accounts():
    if not current_user or current_user.role != 'admin':
        print("Access Denied: Only administrators can view all accounts.")
        input("Press Enter to continue...")
        return

    accounts, msg = admin_ops.get_all_accounts()
    if accounts:
        print("\n--- All System Accounts ---")
        for acc in accounts:
            print(f"ID: {acc.id}, User ID: {acc.user_id}, Account No: {acc.account_number:<12}, "
                  f"Type: {acc.account_type.capitalize():<10}, Balance: {acc.balance:.2f}")
    else:
        print("No accounts found in the system.")
    print(msg)
    input("Press Enter to continue...")


def handle_admin_view_transactions():
    if not current_user or current_user.role != 'admin':
        print("Access Denied: Only administrators can view all transactions.")
        input("Press Enter to continue...")
        return

    transactions, msg = admin_ops.get_all_transactions()
    if transactions:
        print("\n--- All System Transactions ---")
        for txn in transactions:
            description_display = txn.description if txn.description else 'N/A'
            print(f"Acc ID: {txn.account_id}, Type: {txn.type:<12} Amount: {txn.amount:9.2f} "
                  f"Timestamp: {txn.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                  f"Desc: {description_display[:30].ljust(30)}")
    else:
        print("No transactions found in the system.")
    print(msg)
    input("Press Enter to continue...")


def handle_admin_search_user():
    if not current_user or current_user.role != 'admin':
        print("Access Denied: Only administrators can search users.")
        input("Press Enter to continue...")
        return

    print("\n--- Search User by Username ---")
    username_query = input("Enter part of username to search: ").strip()
    users, msg = admin_ops.search_user_by_username(username_query)
    if users:
        print(f"\n--- Search Results for '{username_query}' ---")
        for user in users:
            print(f"ID: {user.id}, Username: {user.username:<15}, Role: {user.role:<8}, Active: {user.is_active}")
    else:
        print("No users found matching your query.")
    print(msg)
    input("Press Enter to continue...")


def run_app():
    global current_user
    while True:
        if current_user:
            if current_user.role == 'user':
                choice = user_menu()
                if choice == '1':
                    handle_view_accounts()
                elif choice == '2':
                    handle_create_account()
                elif choice == '3':
                    handle_deposit()
                elif choice == '4':
                    handle_withdraw()
                elif choice == '5':
                    handle_transfer()
                elif choice == '6':
                    handle_transaction_history()
                elif choice == '7':
                    current_user = None  # Log out the user
                    print("\nSuccessfully logged out.")
                    input("Press Enter to continue...")
                else:
                    print("Invalid choice. Please try again.")
            elif current_user.role == 'admin':
                choice = admin_menu()
                if choice == '1':
                    handle_admin_view_users()
                elif choice == '2':
                    handle_admin_toggle_user_status()
                elif choice == '3':
                    handle_admin_view_accounts()
                elif choice == '4':
                    handle_admin_view_transactions()
                elif choice == '5':
                    handle_admin_search_user()
                elif choice == '6':
                    current_user = None  # Log out the admin
                    print("\nSuccessfully logged out.")
                    input("Press Enter to continue...")
                else:
                    print("Invalid choice. Please try again.")
            else:
                print("Unknown user role. Logging out...")
                current_user = None
                input("Press Enter to continue...")
        else:
            choice = main_menu()
            if choice == '1':
                handle_registration()
            elif choice == '2':
                handle_login()
            elif choice == '3':
                print("Exiting Bank Management System. Goodbye!")
                sys.exit()
            else:
                print("Invalid choice. Please try again.")


if __name__ == "__main__":
    run_app()
