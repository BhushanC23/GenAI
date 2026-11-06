
# KubeCoach - Interactive Menu

while True:
  
    print("1. About KubeCoach")
    print("2. Sample Kubernetes Questions")
    print("3. Check Kubernetes Topic")
    print("0. Exit")
    
    choice = input("Enter your choice: ")

    if choice == "1":
        print("\nKubeCoach explains Kubernetes concepts")
        print("and kubectl commands in simple English.")

    elif choice == "2":
        print("\nSample Questions:")
        print("1. What is a Pod?")
        print("2. What is a Deployment?")
        print("3. What is a Kubernetes Service?")

    elif choice == "3":
        topic = input("Enter a Kubernetes topic: ").lower()

        if topic in ["pod", "deployment", "service"]:
            print("This is a supported sample topic!")
        else:
            print("Topic not in this sample list.")

    elif choice == "0":
        print("Thank you for using KubeCoach!")
        break
    else:
        print("Invalid choice. Please try again.")
