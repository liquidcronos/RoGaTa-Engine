import numpy as np
import cv2
import cv2.aruco as aruco
import rospy
from rogata_engine.srv import *
from geometry_msgs.msg import Pose2D
from nav_msgs.msg import Odometry

class game_object:
    """A class defining the most basic game objects of the engine
    
    :param string name: The name of the object
    :param area: A array containin all borders of the object as a `contour <https://docs.opencv.org/3.4/d4/d73/tutorial_py_contours_begin.html>`
    :type area: numpy array
    :param holes: Array specifying which border constitutes a inner or outer border
    :type holes: numpy array
    """

    def __init__(self,name,area,holes):

        self.name = name
        self.area=area
        self.holes=holes


    def is_inside(self,point):
        """Checks wheter a point is inside the area of the object
        
        A point directl on the border is also considered inside

        :param point: A point which is to be checked
        :type point: 2D numpy array
        :returns: a truthvalue indicating wheter or not the point  is inside the game object
        :rtype: bool

        
        """


        #TODO use the hole_spec tree to build the needet logic statement for detemining inside and outside of an arrea
        point=tuple(point)
        
        inside_contour=np.zeros(len(self.area))
        for i in range(len(self.area)):
            inside_contour[i]= cv2.pointPolygonTest(self.area[i],point,False) != -1

        inside = False
        for i in range(int(min(np.abs(self.holes))),int(max(np.abs(self.holes)))+1):
            holes =  np.argwhere(self.holes == -i)
            areas =  np.argwhere(self.holes ==  i)
            
            inside_hole = False
            for hole in holes:
                inside_hole = inside_hole or inside_contour[hole]

            inside_area = False
            for area in areas:
                inside_area = inside_area or inside_contour[area]

            inside = inside or (inside_area and not inside_hole)

        return bool(inside)

    def shortest_distance(self,point):
        """calculates the shortest distance between the point and the border of the object
        
        Also returns a positive distance when inside the object

        :param point: A 2D point which is to be checked
        :type point: numpy array
        :returns: distance to border of the object
        :rtype: scalar

        
        """

        point=tuple(point)
        min_dist = np.inf
        for i in range(len(self.area)):
            min_dist=np.minimum(np.abs(cv2.pointPolygonTest(self.area[i],point,True)),min_dist)
        return min_dist

    def line_intersect(self,start,direction,length,iterations=100,precision=0.001):
        """calculates the intersection between a line and the border of the object
        
        Iterations and precision are kept at standart values if non are provided

        :param start: a 2D point which specifies the start of the line
        :type start: numpy array
        :param direction: a normalized vector specifiying the direction of the line
        :type direction: numpy array
        :param length: a scalar specifiying the maximum length of the line
        :type length: scalar
        :param iterations: the number of iterations for the ray marching algorithm used (Default value = 100)
        :type iterations: scalar
        :param precision: the precision with which the intersection is being calculated (Default value = 0.001)
        :type precision: scalar
        :returns: 2D position of the intersection
        :rtype: numpy array

        
        """
        position = start
        default  = start+length*direction/np.linalg.norm(direction)
        for k in  range(iterations):
            shortest_dist = self.shortest_distance(position)
            position      = position + shortest_dist*direction/np.linalg.norm(direction)

            if np.linalg.norm(position-start) >= length:
                break
            if shortest_dist <= precision:
                default=position
                break
            
        return default

    def get_position(self):
        """returns the position of the objects center
        
        The center in this case refers to the mean position of the object.
        For a disjointed area this center can be outside of the object itself.


        :returns: 2D position of the objects center

        :rtype: numpy array

        
        """
        cx   = 0
        cy   = 0
        size = 0
        for contours in self.area:
            moments  = cv2.moments(contours)
            cx   = cx   + moments['m10']
            cy   = cy   + moments['m01']
            size = size + moments['m00']
        return np.array([int(cx/float(size)),int(cy/float(size))])

    def move_object(self,new_pos,rotate=0):
        """moves the object to a new position and orientation

        :param new_pos: new 2D position of the object
        :type new_pos: numpy array
        :param rotate: angle of rotation in radians (Default value = 0)
        :type rotate: scalar

        
        """
        cx   = 0
        cy   = 0
        size = 0
        for contours in self.area:
            moments  = cv2.moments(contours)
            cx   = cx   + moments['m10']
            cy   = cy   + moments['m01']
            size = size + moments['m00']
        current_center = np.array([int(cx/float(size)),int(cy/float(size))])
        #current_center   = self.get_position()
        for i in range(len(self.area)):
            centered_contour = self.area[i] - current_center
            #xs, ys = centered_contour[:, 0], centered_contour[:, 1]

            #thetas, rhos = cart2pol(xs, ys)
            #thetas       = thetas + rotate
            #xs, ys       = pol2cart(thetas, rhos)

            #centered_contour[:,0] = xs
            #centered_contour[:,1] = ys
            self.area[i]=centered_contour+new_pos

class dynamic_object(game_object):
    """A subclass of the basic :py:class:`game_object`. 

    Dynamic objects are able to change their position and can be tracked via aruco markers.
    Their current position is published by each :py:class`scene` containing them.

    Instead of initializing the object using a contour a dictionary describing a hitbox needs to be provided.
    The dynamic object then builds the contour.

    Currently only rectangular hitboxes are supported. The dictionary of such a hitbox can be set up as follows:
    ::

        {'type':'rectangle','height':HEIGHT,'width':WIDTH}

    Where HEIGHT and WIDTH are the objects height and width in the game area.


    :param string name: The name of the object
    :param hitbox: A dictionary describing the shape of the objects contour
    :type hitbox: dictionary
    :param ID: The ID of an aruco marker which can be used to track the object
    :param initial_ori: The inital orientation of the object in radians. Standart value is 0
    ;type number:
    """
    def __init__(self,name,hitbox,ID,initial_ori=0):
        if hitbox['type']=='rectangle':
            height = hitbox['height']
            width  = hitbox['width']
            area   = np.array([[0,0],[0,height],[width,height],[width,0]], dtype=np.int32)
        holes = np.array([1])
        game_object.__init__(self,name,np.array([area]),holes)

        self.ID          = ID
        self.orientation = initial_ori
    


class scene():
    """A class implemennting scene objects comprised of multiple :py:class:`game_object` objects.
    It offers Ros Client interfaces which allow other nodes to request information about the game objects.
    the communication interfaces are described in the `documentation <https://rogata-engine.readthedocs.io/en/latest/how_it_works.html#scenes>`_

    :param game_object_list: A list of containing  :py:class`game_object` objects.
    """
    
    def __init__(self,game_object_list):
        self.game_objects={}
        self.object_list = []
        self.dynamic_object_list = []
        for objects in game_object_list:
            self.game_objects[objects.name] = objects
            self.object_list.append(objects.name)
            if isinstance(objects,dynamic_object):
               rospy.set_param(objects.name+"/id",objects.ID)
               self.dynamic_object_list.append(objects.name)


        rospy.set_param("scene_objects",self.object_list)

        pos_serv    = rospy.Service('set_position'  ,SetPos       ,self.handle_set_position)
        pos_g_serv  = rospy.Service('get_position'  ,GetPos       ,self.handle_get_position)
        dist_serv   = rospy.Service('get_distance'  ,RequestDist  ,self.handle_get_distance)
        inters_serv = rospy.Service('intersect_line',RequestInter ,self.handle_line_intersect)
        inside_serv = rospy.Service('check_inside'  ,CheckInside  ,self.handle_inside_check)
       
        publisher_dict={}
        for object_names in self.dynamic_object_list:
            publisher_dict[object_names]=rospy.Publisher(object_names+"/odom",Odometry,queue_size=1)

        rate=rospy.Rate(30)  #hz
        while not rospy.is_shutdown():
            for object_names in self.dynamic_object_list:
                current_object    = self.game_objects[object_names]
                current_publisher = publisher_dict[object_names]
                pose              = current_object.get_position()

                position                         = Odometry()
                position.pose.pose.position.x    = pose[0]
                position.pose.pose.position.y    = pose[1]
                position.pose.pose.orientation.z = current_object.orientation
                current_publisher.publish(position)
            rate.sleep()



    def __del__(self):
        for elements in self.object_list:
            if rospy.has_param(elements+"_id"):
                rospy.delete_param(elements+"_id")
        if rospy.has_param("scene_objects"):
            rospy.delete_param("scene_objects")


    def handle_set_position(self,request):
        """Handles requests to the ``set_position`` ROS service server

        :param request: 
        :type request: SetPosRequest

        """
        choosen_object = self.game_objects[request.object]
        pos            = np.array([request.x,request.y])
        choosen_object.move_object(pos)
        return SetPosResponse(1)

    def handle_get_position(self,request):
        """Handles requests to ``get_position`` ROS service server

        :param request:
        :type request: GetPosRequest

        """
        choosen_object = self.game_objects[request.object]
        pos            = choosen_object.get_position()
        return GetPosResponse(pos[0],pos[1])

    def handle_line_intersect(self,request):
        """Handles requests to  the ``intersect_line`` ROS service server

        :param request: 
        :type request: RequestInterRequest

        """
        choosen_object = self.game_objects[request.object]
        origin         = np.array([request.line.x,request.line.y])
        direction      = np.array([np.cos(request.line.theta),np.sin(request.line.theta)])
        length         = request.length
        intersect      = choosen_object.line_intersect(origin,direction,length)
        return RequestInterResponse(intersect[0],intersect[1])

    def handle_get_distance(self,request):
        """Handles requests to the ``get_distance`` ROS service server

        :param request: 
        :type request: RequestDistRequest

        """
        choosen_object = self.game_objects[request.object]
        point          = np.array([request.x,request.y])
        dist           = choosen_object.shortest_distance(point)
        return RequestDistResponse(dist)

    def handle_inside_check(self,request):
        """Handles requests to the ``check_inside`` ROS service server

        :param request: 
        :type request: CheckInsideRequest

        """
        choosen_object = self.game_objects[request.object]
        point          = np.array([request.x,request.y])
        inside         = bool(choosen_object.is_inside(point))
        return CheckInsideResponse(inside)

   
class rogata_helper():
    """A class for people unfarmiliar with ROS.

    It abstracts the ROS service communication with the :py:class:`scene` class into simply python functions.
    
    
    """
    def __init__(self):
        rospy.wait_for_service('intersect_line')
        self.available_objects = rospy.get_param("scene_objects")

        self.abstract_set_position   = rospy.ServiceProxy('set_position',SetPos,self.set_pos)
        self.abstract_get_position   = rospy.ServiceProxy('get_position',GetPos,self.get_pos)
        self.abstract_line_intersect = rospy.ServiceProxy('intersect_line',RequestInter,self.intersect)
        self.abstract_get_distance   = rospy.ServiceProxy('get_distance',RequestDist,self.dist)
        self.abstract_check_inside   = rospy.ServiceProxy('check_inside',CheckInside,self.inside)

    def set_pos(self,game_object,position):
        """Abstracts the ``set_position`` ROS service communication to set the position of a :py:class:`game_object`

        :param game_object: The name of the game object
        :type game_object: string
        :param position: The new position of the object
        :type position: 2D numpy array

        """
        req  = SetPosRequest(game_object,position[0],position[1])
        try:
            rospy.wait_for_service('set_position',0.5)
            resp = self.abstract_set_position(req)
            return resp
        except rospy.ServiceException as e:
            print("Service call failed: %s"%e)

    def get_pos(self,game_object):
        """Abstracts the ``get_position`` ROS service communication to set the position of a :py:class:`game_object`

        :param game_object: The name of the game object
        :type game_object: string

        """
        req  = GetPosRequest(game_object)
        try:
            rospy.wait_for_service('get_position',0.5)
            resp = self.abstract_get_position(req)
            return np.array([resp.x,resp.y])
        except rospy.ServiceException as e:
            print("Service call failed: %s"%e)

    def intersect(self,game_object,start_point,direction,length):
        """Abstracts the ``intersect_line`` ROS service communication to get the intersection between a :py:class:`game_object` and a line

        :param game_object: The name of the game object to intersect with
        :type game_object: string
        :param start_point: The start of the line
        :type start_point: 2D numpy array
        :param direction: The direction of the line as an angle following ROS convetion
        :type direction: scalar
        :param length: The length of the line 
        :type length: scalar

        """
        line = Pose2D(start_point[0],start_point[1],direction)
        req  = RequestInterRequest(game_object,line,length)
        try:
            rospy.wait_for_service('intersect_line',0.5)
            resp = self.abstract_line_intersect(req)
            return np.array([resp.x,resp.y])
        except rospy.ServiceException as e:
            print("Service call failed: %s"%e)

    def dist(self,game_object,point):
        """Abstracts the ``get_distance`` ROS service communication to get the distance between a :py:class:`game_object` and a point

        :param game_object: The name of the game object whoose distance should be measured
        :type game_object: string
        :param point: the point to which the distance should be measured
        :type point: 2D numpy array

        """
        req  = RequestDistRequest(game_object,point[0],point[1])
        try:
            rospy.wait_for_service('get_distance',0.5)
            resp = self.abstract_get_distance(req)
            return resp.distance
        except rospy.ServiceException as e:
            print("Service call failed: %s"%e)

    def inside(self,game_object,point):
        """Abstracts the ``check_inside`` Ros Service communication to check wheter a given point is inside of a :py:class:`game_object`


        :param game_object: the name of the game object to check
        :type game_object: string
        :param point:  The point to check
        :type point: 2D numpy array

        """
        req  = CheckInsideRequest(game_object,point[0],point[1])
        try:
            rospy.wait_for_service('check_inside',0.5)
            resp = self.abstract_check_inside(req)
            return resp.inside
        except rospy.ServiceException as e:
            print("Service call failed: %s"%e)






def track_dynamic_objects(gray_image,object_name_list):
    """Function which automatically tracks a list of :py:class:`dynamic_object`  that are part of a :py:class:`scene`

    The functions returns no position and instead updates the internal state of each :py:class:`dynamic_object`.
    This position can be accessed using the interfaces of the :py:class:`scene` containing the objects.

    :param gray_image: A grayscale image in which the objects should be tracked
    :param object_name_list: A list of containing the names of the objects that should be tracked

    """

    set_position=rospy.ServiceProxy('set_position',SetPos)
    available_marker_list     = []
    available_marker_id_list = []
    for object_name in object_name_list:
        if rospy.has_param(object_name+"_id"):
            marker_id = rospy.get_param(object_name+"_id")

            available_marker_id_list.append(marker_id)
            available_marker_list.append(object_name)

    new_pos_dict = track_aruco_marker(gray_image,available_marker_id_list)

    for i in range(len(available_marker_id_list)):
        object_name = available_marker_list[i]
        new_pos     = new_pos_dict[available_marker_id_list[i]]
        req         = SetPosRequest(object_name, new_pos[0] , new_pos[1])
        resp        = set_position(req)
        return 1
    else:
        return 0
    

def track_aruco_marker(gray_image,marker_id_list):
    """Tracks a list of aruco markers

    Returns None if the marker was not found in gray_image

    :param gray_image: A grayscale image in which the marker is to be found
    :param marker_id_list: A list of marker ids
    :type marker_id_list: list of numbers

    :returns: A dictionary of marker positions with the marker_ids as keys
    """
    aruco_dict = aruco.Dictionary_get(aruco.DICT_4X4_250)
    parameters = aruco.DetectorParameters_create()
    corners, ids, rejectedImgPoints = aruco.detectMarkers(gray_image, aruco_dict, parameters=parameters)

    center_dict={}
    for marker_id in marker_id_list:
        try:
            if marker_id not in ids:
                center_dict[marker_id]=None
            else:
                indice=np.where(ids == marker_id)
                center = np.sum(corners[indice[0][0]][indice[1][0]],axis=0)/4
                center_dict[marker_id]=center
        except:
            center_dict[marker_id]=None
    return center_dict




def detect_area(hsv_img,lower_color,upper_color,marker_id,min_size,draw=False):
    """Detects the contour of an object containing a marker based on color
    
    It always returns the smallest contour which still contains the marker
    The contour is detected using an image with hsv color space to be robust under different lighting conditions.
    If draw=True the systems draws all found contours as well as the current smalles one containing the marker onto hsv_img

    :param hsv_image: a Image in hsv color space in which the contours  should be detected
    :type hsv_image: numpy array
    :param lower_color: a 3x1 array containing the lower boundary for the color detection
    :type lower_color: numpy array
    :param upper_color: a 3x1 array containing the upper boundary for the color detection
    :type upper_color: numpy array
    :param marker_id: the ID of a 4x4 aruco marker which identifies the object
    :type marker_id: scalar
    :param hsv_img: 
    :param min_size: 
    :param draw:  (Default value = False)
 
    """

    # color detection
    if lower_color[0] <=0:
        second_lower    = lower_color
        second_lower[0] = 179+lower_color[0]
        second_upper    = upper_color
        second_upper[0] = 179

        lower_color[0] = 0
        
        mask1 =cv2.inRange(hsv_img,lower_color,upper_color)
        mask2 =cv2.inRange(hsv_img,second_lower,second_upper)
        mask= mask1 | mask2
    else:
        mask =cv2.inRange(hsv_img,lower_color,upper_color)

    #TODO carefull depending on opencv version the return may be different
    contours, hierachy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    

    #marker detection:
    split_hsv    = cv2.split(hsv_img)
    gray         = split_hsv[2]
    center_dict  =  track_aruco_marker(gray,[marker_id])
    center       = center_dict[marker_id]

    if np.any(center != None):
        if draw == True:
            cv2.drawContours(hsv_img, contours, -1, (0,255,255),3)
            cv2.circle(hsv_img,(center[0],center[1]),7,(90,255,255),7)

        #TODO smallest contour should be real contour encompassing whole image
        row, col =hsv_img.shape[:2]
        smallest_contour = np.array([[0,0],[0,row],[col,row],[col,0]])
        #TODO not needet with real contour
        contour_found    = 0
        for i in range(len(contours)):
            marker_in_contour = True

            marker_in_contour = cv2.pointPolygonTest(contours[i],tuple(center),False) > 0
            marker_in_contour = marker_in_contour and cv2.contourArea(contours[i]) >= min_size
            if  marker_in_contour:
                if cv2.contourArea(contours[i]) <= cv2.contourArea(smallest_contour):
                    contour_found = 1
                    smallest_contour = contours[i]

        if contour_found == 1:
            if draw == True:
                cv2.drawContours(hsv_img, smallest_contour, -1, (90,255,255),6)
            return smallest_contour

    return None


def cart2pol(x, y):
    """Converts a point (x,y) into polar coordinates (theta, rho)

    """
    theta = np.arctan2(y, x)
    rho = np.hypot(x, y)
    return theta, rho


def pol2cart(theta, rho):
    """Converts polar coordinates (theta, rho) into cartesian coordinates (x,y)

    """
    x = rho * np.cos(theta)
    y = rho * np.sin(theta)
    return x, y

