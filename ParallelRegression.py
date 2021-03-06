import sys
import os
import argparse
import numpy as np
from operator import add
from time import time
from pyspark import SparkContext


def readData(input_file, spark_context):
    """  Read data from an input file and return rdd containing pairs of the form:
                         (x,y)
         where x is a numpy array and y is a real value. The input file should be a
         'comma separated values' (csv) file: each line of the file should contain x
         followed by y. For example, line:

         1.0,2.1,3.1,4.5

         should be converted to tuple:

         (array(1.0,2.1,3.1),4.5)
    """
    return spark_context.textFile(input_file) \
        .map(lambda line: line.split(',')) \
        .map(lambda words: (words[:-1], words[-1])) \
        .map(lambda inp: (np.array([float(x) for x in inp[0]]), float(inp[1])))


def readBeta(input):
    """ Read a vector β from CSV file input
    """
    with open(input, 'r') as fh:
        str_list = fh.read().strip().split(',')
        return np.array([float(val) for val in str_list])


def writeBeta(output, beta):
    """ Write a vector β to a CSV file ouptut
    """
    with open(output, 'w') as fh:
        fh.write(','.join(map(str, beta.tolist())) + '\n')


def estimateGrad(fun, x, delta):
    """ Given a real-valued function fun, estimate its gradient numerically.
    """
    d = len(x)
    grad = np.zeros(d)
    for i in range(d):
        e = np.zeros(d)
        e[i] = 1.0
        grad[i] = (fun(x + delta * e) - fun(x)) / delta
    return grad


def lineSearch(fun, x, grad, a=0.2, b=0.6):
    """ Given function fun, a current argument x, and gradient grad,
        perform backtracking line search to find the next point to move to.
        (see Boyd and Vandenberghe, page 464).

        Parameters a,b  are the parameters of the line search.

        Given function fun, and current argument x, and gradient  ∇fun(x), the function finds a t such that
        fun(x - t * grad) <= fun(x) - a t <∇fun(x),∇fun(x)>

        The return value is the resulting value of t.
    """
    t = 1.0
    while fun(x - t * grad) > fun(x) - a * t * np.dot(grad, grad):
        t = b * t
    return t


def predict(x,beta):
    """ Given vector x containing features and parameter vector β,
        return the predicted value:


                        y = <x,β>
    """
    return np.dot(beta.transpose(),x)


def f(x,y,beta):
    """ Given vector x containing features, true label y,
        and parameter vector β, return the square error:

                 f(β;x,y) =  (y - <x,β>)^2
    """
    square_error = (y-np.dot(beta.transpose(),x))**2
    return square_error



def localGradient(x, y, beta):
    """ Given vector x containing features, true label y,
        and parameter vector β, return the gradient ∇f of f:

                ∇f(β;x,y) =  -2 * (y - <x,β>) * x

        with respect to parameter vector β.

        The return value is  ∇f.
    """
    pred_score = np.dot(beta.transpose(), x)
    gradient_decent = -2 * (y - pred_score) * x
    return gradient_decent


def F(data, beta, lam=1.0):
    """  Compute the regularized mean square error:

             F(β) = 1/n Σ_{(x,y) in data}    f(β;x,y)  + λ ||β ||_2^2
                  = 1/n Σ_{(x,y) in data} (y- <x,β>)^2 + λ ||β ||_2^2

         where n is the number of (x,y) pairs in RDD data.

         Inputs are:
            - data: an RDD containing pairs of the form (x,y)
            - beta: vector β
            - lam:  the regularization parameter λ

         The return value is F(β).
    """
    n = data.count()
    mean_square_error = 1/n * data.map(lambda pair: f(pair[0], pair[1], beta)).reduce(lambda x, y: x + y)
    regularised_mean_square_error = mean_square_error + lam * np.dot(beta, beta)
    return regularised_mean_square_error


def gradient(data, beta, lam = 1.0):
    """ Compute the gradient  ∇F of the regularized mean square error
                F(β) = 1/n Σ_{(x,y) in data} f(β;x,y) + λ ||β ||_2^2
                     = 1/n Σ_{(x,y) in data} (y- <x,β>)^2 + λ ||β ||_2^2

        where n is the number of (x,y) pairs in data.

        Inputs are:
             - data: an RDD containing pairs of the form (x,y)
             - beta: vector β
             - lam:  the regularization parameter λ

        The return value is an array containing ∇F.
    """
    n = data.count()

    gd_temp = data.map(lambda pair: localGradient(pair[0], pair[1], beta)).reduce(lambda v1,v2: v1 + v2)

    gd = 1./n*gd_temp + 2 * lam * beta

    return gd


def test(data, beta):
    """ Compute the mean square error

        	 MSE(β) =  1/n Σ_{(x,y) in data} (y- <x,β>)^2

        of parameter vector β over the dataset contained in RDD data, where n is the size of RDD data.

        Inputs are:
             - data: an RDD containing pairs of the form (x,y)
             - beta: vector β

        The return value is MSE(β).
    """
    return F(data, beta)



def train(data, beta_0, lam, max_iter, eps):
    """ Perform gradient descent:

        to  minimize F given by

             F(β) = 1/n Σ_{(x,y) in data} f(β;x,y) + λ ||β ||_2^2

        where
             - data: an rdd containing pairs of the form (x,y)
             - beta_0: the starting vector β
             - lam:  is the regularization parameter λ
             - max_iter: maximum number of iterations of gradient descent
             - eps: upper bound on the l2 norm of the gradient
             - a,b: parameters used in backtracking line search

        The function performs gradient descent with a gain found through backtracking
        line search. That is it computes

                   β_k+1 = β_k - γ_k ∇F(β_k)

        where the gain γ_k is given by

        	  γ_k = lineSearch(F,β_κ,∇F(β_k))

        and terminates after max_iter iterations or when ||∇F(β_k)||_2<ε.

        The function returns:
             -beta: the trained β,
             -gradNorm: the norm of the gradient at the trained β, and
             -k: the number of iterations performed
    """
    def some_fun(beta):
        mse = F(data,beta,lam)
        return mse
    k = 0
    beta = beta0
    norm_grad = np.linalg.norm(gradient(data,beta,lam))
    start = time()
    while (k < max_iter and eps < norm_grad):
        gd = gradient(data, beta, lam)
        MSE = F(data,beta,lam)
        gamma = lineSearch(some_fun, beta, gd)
        beta = beta - gamma * gd
        norm_grad = np.linalg.norm(gd)
        print("Iteration: ",str(k),"Time: ",str(time()-start),"||∇F(β_k)|| ",str(norm_grad),"F(β_k)",str(MSE))
        k += 1

    return beta,norm_grad,k



def prepare(data):
    """ Prepare data for aggregating terms,

        where
            - data: an rdd containing pairs of the form (x, y)

        Each (x, y) pair is mapped to

            (x*transpose(x), y*x)

        The function returns:
            - prepared_data: an rdd containing pairs of the form (x*transpose(x), y*x)
    """
    prep_data = data.map(lambda pair:((pair[0] * np.transpose(pair[0])),pair[1] * pair[0]))
    return prep_data



def aggregate(data, lam):
    """ Aggregate terms to a matrix and a vector, which form a system of linear equations,

        where
            - data: an rdd containing pairs of the form (x_i, y_i)
            - lam: hyperparameter used in calculations, λ

        This function uses input data to generate the matrix

            1/n*transpose(X)*X + λI

        and the vector

            1/n*transpose(X)*y.

        where n is the number of tuples, i.e. data samples and

            X = [x_i] i = 1, ..., n is an n by d matrix and
            y = [y_i] i = 1, ..., n is a vector

        both with real entries.

        The function returns:
            - aggregated_data: the tuple (1/n*transpose(X)*X + λI, 1/n*transpose(X)*y), in given order
    """
    # v = data.count()
    ide = np.identity(50)
    # f = prepare(data).keys() + lam * ide
    n = data.count()
    x = data.keys().reduce(lambda x,y: x+y)
    y = data.values().reduce(lambda x,y: x+y)

    first_term = (1./n * np.dot(x,np.transpose(x))) + lam * ide
    second_term = 1./n * np.dot(np.transpose(x),y)
    return (first_term,second_term)

def solve_beta(data, lam):
    """ Solve the linear system of equations:

        (1/n*transpose(X)*X + λI)*β = 1/n*transpose(X)*y

        where
            - data: an rdd containing pairs of the form (x_i, y_i)
            - lam: hyperparameter λ used in calculations


        The function returns:
            - beta: β computed via the numpy "linalg.solve" linear system solver
    """
    start = time()
    print("Aggregating data...")
    A, b = aggregate(data, lam)
    agg_time = time()
    print("...done. Aggregation time:", agg_time - start)
    print("Solving linear system...")
    return np.linalg.solve(A, b)
    sol_time = time()
    print("...done. System solution time:", sol_time - agg_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parallel Ridge Regression.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--traindata', default=None,
                        help='Input file containing (x,y) pairs, used to train a linear model.')
    parser.add_argument('--testdata', default=None,
                        help='Input file containing (x,y) pairs, used to test a linear model.')
    parser.add_argument('--beta', default='beta',
                        help='File where beta is stored (when training) and read from (when testing).')
    parser.add_argument('--lam', type=float, default=0.0, help='Regularization parameter λ.')
    parser.add_argument('--max_iter', type=int, default=100, help='Maximum number of iterations.')
    parser.add_argument('--eps', type=float, default=0.01,
                        help='ε-tolerance. If ||∇F(β_k)||_2<ε, i.e., the Euclidan norm of the gradient is smaller than ε, gradient descent terminates.')
    parser.add_argument('--N', type=int, default=20, help='Number of partitions')
    parser.add_argument('--solver', default='GD', choices=['GD', 'LS'],
                        help='GD learns β via gradient descent, LS learns β by solving a linear system of equations')

    args = parser.parse_args()

    sc = SparkContext(appName='Parallel Ridge Regression')
    sc.setLogLevel('warn')

    beta = None

    if args.traindata is not None:
        # Train a linear model β from data with regularization parameter λ, and store it in beta
        print('Reading training data from', args.traindata)
        data = readData(args.traindata, sc)
        data = data.repartition(args.N).cache()

        x, y = data.take(1)[0]
        beta0 = np.zeros(len(x))

        if args.solver == 'GD':
            start = time()
            print('Training on data from', args.traindata, 'with λ =', args.lam, ', ε =', args.eps, ', max iter = ',
                  args.max_iter)
            beta, gradNorm, k = train(data, beta_0=beta0, lam=args.lam, max_iter=args.max_iter, eps=args.eps)
            print('Algorithm ran for', k, 'iterations. Converged:', gradNorm < args.eps, 'Training time:',
                  time() - start)
            print('Saving trained β in', args.beta)
            writeBeta(args.beta, beta)

        else:
            start = time()
            print('Solving the linear system for β on data from', args.traindata, 'with λ =', args.lam)
            beta = solve_beta(data, args.lam)
            print('Training time:', time() - start)
            print('Saving solved β in', args.beta)
            writeBeta(args.beta, beta)

    if args.testdata is not None:
        # Read beta from args.beta, and evaluate its MSE over data
        print('Reading test data from', args.testdata)
        data = readData(args.testdata, sc)
        data = data.repartition(args.N).cache()

        print('Reading β from', args.beta)
        beta = readBeta(args.beta)

        print('Computing MSE on data', args.testdata)
        MSE = test(data, beta)
        print('MSE is:', MSE)

