from __future__ import print_function, with_statement

import tensorflow as tf
from sklearn.utils import shuffle
import random
import pdb

from data.convertmidi import *
from data.convert import *

print("Running tf version {}".format(tf.__version__))

# Hyperparameters
TIME_STEPS = 64
N_FEATURES = 128
N_EMBED = 128
N_HIDDEN = 128
# N_OUTPUT = 349632 # 128 choose 2 + 128 choose 3 + 128
N_OUTPUT = N_FEATURES
N_EPOCHS = 150 # Seem to need to train for 100 to get anything
BATCH_SIZE = 5
ETA = .01
n_lstm_layers = 2
# keep_prob = 0.5

EPSILON = 0.2

START = 0
N_SEED = TIME_STEPS

def f(X):
	"""
	Custom non-linear activation function for MIDI.
	Ensures velocity is a valid value between 0 and 128
	"""
	return tf.minimum(
		tf.maximum(X, 0),
		128
	)

def sample_bernoulli(p):
	return np.apply_along_axis(
		lambda x: random.random() < x,
		axis=1,
		arr=p,
	).astype(np.int32)

def stats(pred_hold, pred_hit):
	print("Stats:")
	print("  held shape:", pred_hold.shape)
	print("  hit shape:", pred_hit.shape)
	print("  mean notes held / t:", np.mean(np.sum(pred_hold, axis=1)))
	print("  mean notes hit / t:", np.mean(np.sum(pred_hit, axis=1)))
	print("  mean notes held:", np.mean(pred_hold))
	print("  mean notes hit:", np.mean(pred_hit))
	# sparsity = (np.sum(np.count_nonzero(arr)).astype(np.float)) / np.size(arr)
	# print("  shape: {}".format(arr.shape))
	# print("  sparsity (non-zero elements): %{}".format(sparsity * 100))
	# print("  values range from {} to {}".format(np.amin(arr), np.amax(arr)))

training = tf.placeholder_with_default(False, shape=())
keep_prob = tf.cond(training, lambda:tf.constant(0.5), lambda:tf.constant(1.0))

def lstm_dropout_cell():
	lstm = tf.contrib.rnn.BasicLSTMCell(N_HIDDEN)
	lstm_dropout = tf.contrib.rnn.DropoutWrapper(lstm, output_keep_prob=keep_prob) # dropout between lstm layers
	return lstm_dropout

class MusicGen:

	def __init__(self):

		# TODO parametrize constants as args here

		# LSTM cell
		self.stacked_lstm = tf.contrib.rnn.MultiRNNCell([lstm_dropout_cell() for _ in range(n_lstm_layers)])
		# lstm_dropout = tf.contrib.rnn.DropoutWrapper(lstm, output_keep_prob=keep_prob) # dropout between lstm layers
		# self.stacked_lstm = tf.contrib.rnn.MultiRNNCell([lstm_dropout, tf.contrib.rnn.BasicLSTMCell(N_HIDDEN)])

		# Embedding layer parameters
		self.We = tf.get_variable("We", shape=[N_FEATURES * 2, N_EMBED], initializer=tf.contrib.layers.xavier_initializer())
		self.be = tf.get_variable("be", shape=[N_EMBED], initializer=tf.zeros_initializer())

		# Output layer parameters
		self.W = tf.get_variable("W", shape=[N_HIDDEN, N_OUTPUT * 2], initializer=tf.contrib.layers.xavier_initializer())
		self.b = tf.get_variable("b", shape=[N_OUTPUT * 2], initializer=tf.zeros_initializer())

	def add_train_graph(self):

		print("Building train graph..")

		# with tf.name_scope("train"):

		# Input tensors
		self.X_hold = tf.placeholder(tf.float32, shape=[BATCH_SIZE, TIME_STEPS, N_FEATURES])
		self.X_hit = tf.placeholder(tf.float32, shape=[BATCH_SIZE, TIME_STEPS, N_FEATURES])
		X = tf.concat([self.X_hold, self.X_hit], axis=2)

		hidden_state = tf.zeros(shape=[BATCH_SIZE, N_HIDDEN])
		current_state = tf.zeros([BATCH_SIZE, N_HIDDEN])
		state = hidden_state, current_state

		self.loss = 0.

					# LSTM cell
		initial_state = self.stacked_lstm.zero_state(BATCH_SIZE, dtype=tf.float32)

		outputs, state = tf.nn.dynamic_rnn(self.stacked_lstm, X,
									   initial_state=initial_state,
									   dtype=tf.float32)


		y = tf.layers.dense(outputs, N_OUTPUT * 2, activation=None, name='fc')
		y_hold, y_hit = tf.split(y, [N_OUTPUT, N_OUTPUT], axis=2)
		self.loss += tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=y_hold, labels=self.X_hold))
		self.loss += tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=y_hit, labels=self.X_hit))

		self.train_step = tf.train.AdamOptimizer(ETA).minimize(self.loss)

		print("Train graph built successfully!")

	def add_gen_graph(self):

		print("Building gen graph..")

		# with tf.name_scope("train"):

		self.x_hold = tf.placeholder(tf.float32, shape=[BATCH_SIZE, 1, N_FEATURES])
		self.x_hit = tf.placeholder(tf.float32, shape=[BATCH_SIZE, 1, N_FEATURES])
		x = tf.concat([self.x_hold, self.x_hit], axis=2)

		self.hidden_state1 = tf.placeholder(tf.float32, shape=[BATCH_SIZE, N_HIDDEN])
		self.current_state1 = tf.placeholder(tf.float32, shape=[BATCH_SIZE, N_HIDDEN])
		self.hidden_state2 = tf.placeholder(tf.float32, shape=[BATCH_SIZE, N_HIDDEN])
		self.current_state2 = tf.placeholder(tf.float32, shape=[BATCH_SIZE, N_HIDDEN])

		state1 = tf.contrib.rnn.LSTMStateTuple(self.hidden_state1, self.current_state1)
		state2 = tf.contrib.rnn.LSTMStateTuple(self.hidden_state2, self.current_state2)

		state = (state1, state2)

		outputs, state = tf.nn.dynamic_rnn(self.stacked_lstm, x,
									   initial_state=state, #change to (state1,) if 1 layer
									   dtype=tf.float32)

		y = tf.layers.dense(outputs, N_OUTPUT * 2, activation=None, name='fc', reuse=True) #use same weights as in train

		self.y_hold, self.y_hit = tf.split(y, [N_OUTPUT, N_OUTPUT], axis=2)
		self.y_hold = tf.sigmoid(self.y_hold) #softmax
		self.y_hit = tf.sigmoid(self.y_hit)

		# If two layers
		(self.next_hidden_state1, self.next_current_state1), (self.next_hidden_state2, self.next_current_state2) = state

		## Below is if there's only one layer
		# (self.next_hidden_state1, self.next_current_state1), = state
		# self.next_hidden_state2, self.next_current_state2 = self.next_hidden_state1, self.next_current_state1 #not used, just so it has a value

		print("Gen graph build successfully!")
			
	def train(self, X_hold, X_hit, session):
		for epoch in xrange(N_EPOCHS):
			X_hold, X_hit = shuffle(X_hold, X_hit)
			loss = 0.
			for i in xrange(0, len(X_hold) - BATCH_SIZE, BATCH_SIZE):
				batch_loss, _ = session.run([self.loss, self.train_step], feed_dict={
					self.X_hold: X_hold[i:i + BATCH_SIZE, :, :],
					self.X_hit: X_hit[i:i + BATCH_SIZE, :, :],
					training: True
					# self.Y_hold: Y_hold[i:i + BATCH_SIZE, :],
					# self.Y_hit: Y_hit[i:i + BATCH_SIZE, :],
				})
				loss += batch_loss
			print("Epoch {} train loss: {}".format(epoch, loss))

	# TODO this function will not "generate" songs.. but that won't be too different
	def predict(self, x_hold, x_hit, session, length=3600):

		hidden_state1 = np.zeros(shape=[BATCH_SIZE, N_HIDDEN])
		current_state1 = np.zeros(shape=[BATCH_SIZE, N_HIDDEN])
		hidden_state2 = np.zeros(shape=[BATCH_SIZE, N_HIDDEN])
		current_state2 = np.zeros(shape=[BATCH_SIZE, N_HIDDEN])

		nodes = [self.y_hold, self.y_hit, self.next_hidden_state1, self.next_current_state1, self.next_hidden_state2, self.next_current_state2]

		for i in xrange(x_hold.shape[1]):
			y_hold, y_hit, hidden_state1, current_state1, hidden_state2, current_state2 = session.run(nodes, feed_dict={
				self.x_hold: x_hold[:,i:i+1,:],
				self.x_hit: x_hit[:,i:i+1,:],
				self.hidden_state1: hidden_state1,
				self.current_state1: current_state1,
				self.hidden_state2: hidden_state2,
				self.current_state2: current_state2
			})

		# TODO Several options for generation:
		#	* Round each probability
		#	* Sample stochastically according to distribution
		#	* Feed in probability distribution at next prediction

		pred_hold, pred_hit = [], []
		for i in xrange(length):

			y_hold = (y_hold > EPSILON).astype(np.int32)
			y_hit = (y_hit > EPSILON).astype(np.int32)
			# y_hold = sample_bernoulli(y_hold)
			# y_hit = sample_bernoulli(y_hit)

			pred_hold.append(y_hold)
			pred_hit.append(y_hit)

			y_hold, y_hit, hidden_state1, current_state1, hidden_state2, current_state2 = session.run(nodes, feed_dict={
				self.x_hold: y_hold,
				self.x_hit: y_hit,
				self.hidden_state1: hidden_state1,
				self.current_state1: current_state1,
				self.hidden_state2: hidden_state2,
				self.current_state2: current_state2
			})

		return (
			np.stack(pred_hold, axis=1),
			np.stack(pred_hit, axis=1),
		)

crop_data = lambda data: data[:len(data) - (len(data) % TIME_STEPS),:]
stack = lambda data: np.stack(np.split(data, TIME_STEPS, axis=0), axis=1)

if __name__ == "__main__":

	# print("Loading data..")
	# data_o, attributes = midi_encode("data/songs/moonlightinvermont.mid", False)
	# data = np.array(data_o)
	# data = data[:len(data) - (len(data) % TIME_STEPS),:] # Cut off extra stuff
	# stats(data)
	# data =  # Cut song into separate samples of same length
	# # The data should have shape (num_trials, time_steps, num_features)
	# print("Training data of shape {}".format(data.shape))

	print("Loading data..")
	raw_hold, raw_hit, attr = encode("data/songs/3ravens.mid", False)
	raw_hold, raw_hit = map(crop_data, [raw_hold, raw_hit])
	stats(raw_hold, raw_hit)

	# Stack by timesteps
	X_hold, X_hit = map(stack, [raw_hold, raw_hit])

	print("Calculating seed..")
	print(X_hold.shape)
	seed_hold = X_hold[START:START + BATCH_SIZE,:N_SEED, :]
	print(seed_hold.shape)
	seed_hit = X_hit[START:START + BATCH_SIZE,:N_SEED, :]
	stats(seed_hold[0,:,:], seed_hit[0,:,:])

	gen = MusicGen()
	gen.add_train_graph()
	gen.add_gen_graph()

	saver = tf.train.Saver()

	session = tf.Session()
	print("Initializing all variables")
	session.run(tf.global_variables_initializer())

	print("Training..")
	gen.train(X_hold, X_hit, session)
	saver.save(session, "models/recent")
	print("Training completed!")

	print("Restoring..")
	# saver.restore(session, "models/recent")
	print("Model models/recent restored!")

	print("Predicting..")
	pred_hold, pred_hit = gen.predict(seed_hold, seed_hit, session)
	print("Predicted tensors of shapes {}, {}!".format(pred_hold.shape, pred_hit.shape))

	print("Encoding MIDI..")
	pred_hold, pred_hit = pred_hold[0,:,0,:], pred_hit[0,:,0,:]
	stats(pred_hold, pred_hit)
	pattern = decode(pred_hold, pred_hit, attr)
	midi.write_midifile("output.mid", pattern)
	print("MIDI saved!")
