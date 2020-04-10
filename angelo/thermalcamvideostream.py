# From imutils/video/.webcamvideostream.py
# import the necessary packages
from threading import Thread
import cv2

class ThermalcamVideoStream:
	def __init__(self, src=0, name="WebcamVideoStream"):
		# initialize the video camera stream and read the first frame
		# from the stream
		self.stream = cv2.VideoCapture(src)

		# FLIR specific
		self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc('Y', '1', '6', ' '))
		self.stream.set(cv2.CAP_PROP_CONVERT_RGB, False)

		(self.grabbed, self.frame) = self.stream.read()

		# initialize the thread name
		self.name = name

		# initialize the variable used to indicate if the thread should
		# be stopped
		self.stopped = False

	def start(self):
		# start the thread to read frames from the video stream
		t = Thread(target=self.update, name=self.name, args=())
		t.daemon = True
		t.start()
		return self

	def update(self):
		# keep looping infinitely until the thread is stopped
		while True:
			# if the thread indicator variable is set, stop the thread
			if self.stopped:
				return

			# otherwise, read the next frame from the stream
			(self.grabbed, self.frame) = self.stream.read()

	def read(self):
		# return the frame most recently read
		return self.frame

	def stop(self):
		# indicate that the thread should be stopped
		self.stopped = True
