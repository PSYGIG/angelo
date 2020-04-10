def run(module):

  def run_video_pipeline(frame_handler):
    """Running video pipeline

    Logic for grabbing frame and pass it into the frame handler
    Frame handler defined by user side and application logic goes there
    Event is a dependency injecting to the handler and 
    user can dispatch event in order to have some sort of integration on medium
    """

    import time
    import cv2
    from .videostream import VideoStream
    from .event import Event

    cv2.namedWindow("Preview", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Preview", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # by default, it will fetch /dev/video0
    # TODO: use config or have to update manually
    vs = VideoStream(0, useFlirCamera=True).start()
    time.sleep(1.0)  
    # initiate an event tracer instance and inject into the handler
    event = Event()
    # start the frame loop
    while True:
      # grab the frame from the threaded video file stream
      frame = vs.read()
      # module frame handler
      frame = frame_handler(frame, event)

      cv2.imshow("Preview", cv2.resize(frame, (1920, 1080)))
      if cv2.waitKey(10) == 27:
        break

    # stop the streamer
    vs.stop()  

  # ---------------- pipeline ---------------------

  print("{} is running ...".format(module.__MODULE_ID))

  # start the video pipeline
  frame_handler = getattr(module, '__handle_frame', None)
  if (not (frame_handler is None)):
    run_video_pipeline(frame_handler)
