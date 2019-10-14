def run(module):

  def run_video_pipeline(frame_handler):
    """Running video pipeline

    Logic for grabbing frame and pass it into the frame handler
    Frame handler defined by user side and application logic goes there
    Event is a dependency injecting to the handler and 
    user can dispatch event in order to have some sort of integration on medium
    """

    import time
    from imutils.video import VideoStream
    from .event import Event

    # by default, it will fetch /dev/video0
    vs = VideoStream(0).start()
    time.sleep(1.0)  
    # initiate an event tracer instance and inject into the handler
    event = Event()
    # start the frame loop
    while True:
      # grab the frame from the threaded video file stream
      frame = vs.read()
      # module frame handler
      frame_handler(frame, event)

    # stop the streamer
    vs.stop()  

  # ---------------- pipeline ---------------------

  print("{} is running ...".format(module.__MODULE_ID))

  # start the video pipeline
  frame_handler = getattr(module, '__handle_frame', None)
  if (not (frame_handler is None)):
    run_video_pipeline(frame_handler)
