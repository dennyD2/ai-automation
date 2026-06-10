import os

COUNTER_FILE = "test_data/runtime/email_counter.txt"

def generate_unique_email():
    if not os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "w") as f:
            f.write("1000")

    with open(COUNTER_FILE, "r") as f:
        counter = int(f.read().strip())

    counter += 1

    with open(COUNTER_FILE, "w") as f:
        f.write(str(counter))

    email = f"bling2cloud+{counter}@gmail.com"
    print(f"✅ Generated email: {email}")
    
    return email
