# Raft-Implementation

## About the project
- This repository contains a simple [RAFT](https://raft.github.io/raft.pdf) concensus algorithm implemented as part of the [CSE530](https://techtree.iiitd.edu.in/viewDescription/filename?=CSE530) course offered at IIIT-D.
- Team Members: Aditya Ahuja, Deeptanshu Barman, Keshav Rajput

## Introduction
- **Raft** is a consensus algorithm designed to be easy to understand. Raft divides time into terms, and each term begins with an election to select a leader. The leader manages the replication of the log entries to the other servers and ensures a high degree of consistency.
- This implementation of RAFT also employs leader lease for optimized read only queries. Leases can be considered as tokens that are valid for a certain period of time, known as lease duration. A node can serve read and write requests from the client if and only if the node has this valid token/lease.
- For a more detailed explanation please refer the following [page](https://www.yugabyte.com/blog/low-latency-reads-in-geo-distributed-sql-with-raft-leader-leases/#:~:text=This%20is%20shown%20in%20the%20animation%20sequence%20below.).

## Remote Procedure Calls (RPCs) 



