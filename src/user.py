import raft_pb2_grpc
import raft_pb2
import grpc
import time 


ALL_PORTS = [4040, 4041, 4042, 4043]


if __name__ == "__main__":
    print("👋 Welcome to the Raft Consensus Algorithm Menu!")
    leader_id = 0
    while True:
        command = input("Please enter a command (GET/SET):")
        if command == "GET":
            key = input("Please enter the key:")
            request_string = "GET " + key
        elif command == "SET":
            key = input("Please enter the key:")
            value = input("Please enter the value:")
            request_string = "SET " + key + " " + value
        else:
            print("Invalid command. Please try again.")
            
        message = raft_pb2.ServeClientArgs()
        message.Request = str(request_string)
        try:
            print("🚀 Sending request to node with ID-"+str(leader_id))
            channel = grpc.insecure_channel('localhost:'+str(ALL_PORTS[leader_id]))
            stub = raft_pb2_grpc.raft_serviceStub(channel)
            response = stub.serveClient(message)
            if (response.Success):
                print("✅ Success: Request has been processed successfully.")
                print("Response: " + response.Data)
                leader_id = int(response.LeaderID)
            else:
                print("❌ Error: Request could not be processed by server.")
        except Exception as e:
            print("❌ Error: Could not connect to the server. Please try again.")
            leader_id = (leader_id + 1) % 4
        