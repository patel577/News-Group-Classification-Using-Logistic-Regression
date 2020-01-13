# News-Group-Classification-Using-Logistic-Regression
This repository has code for predicting class of the news using logistic regression and compare the performance model run-time with parallel logistic regression using Spark. Both models are made from scratch. 

# Data
http://qwone.com/~jason/20Newsgroups/

# Approach
Goal of the project is to classify the news group into positive and negative class by building logistic regression algorithm from scratch. 
I used argparse library to tune the multiple parameters of model through command line. This is complete machine learning pipeline where you
give input .txt file and pipeline gives you results. I used OOP to make class as Sparsevector({}) to handle the data more efficiently. 

