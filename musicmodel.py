from __future__ import print_function, with_statement

import tensorflow as tf
from sklearn.utils import shuffle

from data.convertmidi import *

print("Running tf version {}".format(tf.__version__))

# Parameters and hyperparameters
TIME_STEPS = 60
N_FEATURES = 128
N_EMBED = 64
N_HIDDEN = 32
N_OUTPUT = N_FEATURES
N_EPOCHS = 10
BATCH_SIZE = 10
ETA = .01

def add_graph():

    print("Building tf graph..")

    # Input tensor
    X = tf.placeholder(tf.float32, shape=[BATCH_SIZE, TIME_STEPS, N_FEATURES])

    # TODO maybe add an embedding layer here?

    # LSTM cell
    lstm = tf.contrib.rnn.BasicLSTMCell(N_HIDDEN)

    # Output layer parameters
    W = tf.Variable(tf.random_normal([N_HIDDEN, N_OUTPUT]))
    b = tf.Variable(tf.zeros([N_OUTPUT]))

    hidden_state = tf.zeros(shape=[BATCH_SIZE, N_HIDDEN])
    current_state = tf.zeros([BATCH_SIZE, N_HIDDEN])
    state = hidden_state, current_state

    predictions = []
    loss = 0.

    for t, x_t in enumerate(tf.unstack(X, axis=1)):

        if t == X.shape[1] - 1: # No prediction for last thing
            continue

        h, state = lstm(x_t, state)
        y = tf.matmul(h, W) + b
        predictions.append(y)
        loss += tf.losses.mean_squared_error(X[:,t + 1,:], y)
        # TODO I think we might want to use something besides MSE? Should check papers

    predictions = tf.stack(predictions, axis=1)

    train = tf.train.AdamOptimizer(ETA).minimize(tf.reduce_sum(loss))

    print("Graph built successfully!")
    return X, predictions, loss, train

def train(X, session):
    for epoch in xrange(N_EPOCHS):
        X = shuffle(X)
        loss = 0.
        for i in xrange(0, len(X) - BATCH_SIZE, BATCH_SIZE):
            batch_X = X[i:i + BATCH_SIZE, :, :]
            batch_loss, _ = session.run([loss_op, train_op], feed_dict={
                X_placeholder: batch_X,
            })
            loss += batch_loss
        print("Epoch {} train loss: {}".format(epoch, loss))

def predict(X, session):
    preds = session.run(predict_op, feed_dict={
        X_placeholder: X,
    })
    return preds

if __name__ == "__main__":

    print("Loading data..")
    data = midi_encode("data/songs/moonlightinvermont.mid")
    data = np.array(data)
    print(data.shape)
    data = data[:len(data) - (len(data) % TIME_STEPS),:] # Cut off extra stuff
    data = np.stack(np.split(data, TIME_STEPS, axis=0), axis=1) # Cut song into separate samples of same length
    # The data should have shape (num_trials, time_steps, num_features)
    print("Training data of shape {}".format(data.shape))

    X_placeholder, predict_op, loss_op, train_op = add_graph()

    session = tf.Session()
    print("Initializing all variables")
    session.run(tf.global_variables_initializer())

    # Can't train anything yet, because we don't have a well-defined loss function............
    # So instead, I test if we can pass shit into the network to get a prediction

    print("Training..")
    train(data, session)
    print("Training completed!")

    print("Predicting..")
    predictions = predict(data[:BATCH_SIZE,:,:], session)
    print("Got prediction tensor of shape {}".format(predictions.shape))
