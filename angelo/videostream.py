# From imutils/video/.videostream.py
# import the necessary packages

class VideoStream:
	def __init__(self, src=0, usePiCamera=False, useFlirCamera=False, resolution=(320, 240),
		framerate=32, **kwargs):
		# check to see if the picamera module should be used

		if usePiCamera:
			# only import the picamera packages unless we are
			# explicity told to do so -- this helps remove the
			# requirement of `picamera[array]` from desktops or
			# laptops that still want to use the `imutils` package
			from imutils.video.pivideostream import PiVideoStream

			# initialize the picamera stream and allow the camera
			# sensor to warmup
			self.stream = PiVideoStream(resolution=resolution,
				framerate=framerate, **kwargs)

		elif useFlirCamera:
			from .thermalcamvideostream import ThermalcamVideoStream
			self.stream = ThermalcamVideoStream(src=src)

		# otherwise, we are using OpenCV so initialize the webcam
		# stream
		else:
			from imutils.video.webcamvideostream import WebcamVideoStream
			self.stream = WebcamVideoStream(src=src)

	def start(self):
		# start the threaded video stream
		return self.stream.start()

	def update(self):
		# grab the next frame from the stream
		self.stream.update()

	def read(self):
		# return the current frame
		return self.stream.read()

	def stop(self):
		# stop the thread and release any resources
		self.stream.stop()
