import numpy,cPickle,array
from decorator import decorator

def memoize(func):
    """
    this is a decorator used to memoize an instance method's output.

    note that this assumes:

        (1) that it is decorating an instance mehtod
        (2) that the arguments to the decorated method (minus the 'self') are
        hashable if put into a tuple.

    usage:
        @memoize
        def blah(self, arg1, arg2):
            '''this will only run once'''
            return some_lengthy_calculation(arg1, arg2)

    """
    def _get(self, *args):
        cache_name = '_' + func.__name__ + '_cache'
        if not hasattr(self, cache_name):
            setattr(self, cache_name, {})
        cache = getattr(self, cache_name)

        key = tuple(args)
        if key not in cache:
            cache[key] = func(self, *args)

        return cache[key]

    return _get

def cached_property(func, name=None):
    """
    this decorator creates a cached property of an instance attribute.
    
    usage:
        @cached_property
        def blah(self):
            '''this will only run once'''
            return some_lengthy_calculation()

    the property can only be gotten, no set/delete methods are defined by this
    decorator
    """
    if name is None :
        name = '_' + func.__name__ 

    def _get(self):
        if not hasattr(self, name):
            setattr(self, name, func(self))
        return getattr(self, name)

    return property(_get)

def smooth(x,window_len=11,window='hanning'):
    """smooth the data using a window with requested size.

    from here:

        http://www.scipy.org/Cookbook/SignalSmooth
    
    This method is based on the convolution of a scaled window with the signal.
    The signal is prepared by introducing reflected copies of the signal (with
    the window size) in both ends so that transient parts are minimized in the
    begining and end part of the output signal.
    
    input:
        x: 
            the input signal 
        window_len:
            the dimension of the smoothing window; should be an odd integer
        window:
            the type of window from 'flat', 'hanning', 'hamming', 'bartlett',
            'blackman' flat window will produce a moving average smoothing.

    output:
        the smoothed signal
        
    example:
        t=linspace(-2,2,0.1)
        x=sin(t)+randn(len(t))*0.1
        y=smooth(x)
    
    see also: 
        numpy.hanning, numpy.hamming, numpy.bartlett, numpy.blackman,
        numpy.convolve, scipy.signal.lfilter
    """

    if x.ndim != 1:
        raise ValueError, "smooth only accepts 1 dimension arrays."

    if x.size < window_len:
        raise ValueError, "Input vector needs to be bigger than window size."


    if window_len<3:
        return x


    allowed_types = ('flat', 'hanning', 'hamming', 'bartlett', 'blackman')
    if not window in allowed_types:
        raise ValueError( '"window" must be one of %s' % \
                ', '.join(t for t in allowed_types))


    s=numpy.r_[x[window_len-1:0:-1],x,x[-1:-window_len:-1]]
    if window == 'flat': #moving average
        w=numpy.ones(window_len,'d')
    else:
        w=eval('numpy.'+window+'(window_len)')

    y=numpy.convolve(w/w.sum(),s,mode='valid')
    return y

def local_extrema(s, combined=False):
    """
    return two lists, one of local mins, one of local maxes
    """
    increasing = None
    for j,v in enumerate(s[1:], 1):
        if v > s[j-1]:
            increasing = True
            break
        elif v < s[j-1]:
            increasing = False
            break

    if increasing == None:
        # we never saw any peaks, return empty output
        return [] if combined else ([], [])

    last = s[j-1]
    mins, maxs = [], []
    for i in xrange(j, len(s)):
        if increasing:
            if s[i] < s[i-1]:
                mins.append(i-1)
                increasing = False
        else:
            if s[i] > s[i-1]:
                maxs.append(i-1)
                increasing = True

    return sorted(mins + maxs) if combined else mins,maxs

def raw_signal(fname):
    """
    convenience function to get a raw signal.

    "fname" is the filename of the signal in S16LE PCM format
    """
    a = array.array('h')
    a.fromstring(open(fname).read())
    return a

class Signal(object):

    # sampling frequency
    FS = 44100.0

    # the size of the window used to check whether we've reached the end of the
    # signal
    END_WIN_LEN = 90                                

    # this is the threshold for deciding the signal has ended.  if the average
    # of the abs value of the amplitude of the last END_WIN_LEN samples dips
    # below this, we've reached the end of the signal
    LOW_AVERAGE = 200.

    # the amplitude that triggers the start of the signal
    START_THRESHOLD = 400.

    # the minimum number of samples between peaks
    MIN_SEPARATION = 10

    # the minimum difference in amplitude from one peak to the next
    GATE = 50

    # the minimum length of time of a swipe (units in seconds)
    MIN_SWIPE_LEN = 0.2

    def __init__(self, raw_signal=[]):
        self.raw_signal = raw_signal;

    @cached_property
    def x(self):
        return numpy.arange(len(self.y)) / self.FS

    @cached_property
    def y(self):
        return numpy.array([ float(i) for i in self.raw_signal ])

    @cached_property
    def start(self):
        for i,s in enumerate(self.y):
            if abs(s) > self.START_THRESHOLD:
                return i
    start_time = cached_property(lambda self: self.start/self.FS)

    @cached_property
    def end(self):
        win = [ self.y[i]
                for i in range(self.start, self.start + self.END_WIN_LEN) ]
        i = self.start + self.END_WIN_LEN
        min_index = self.start + self.END_WIN_LEN + \
                    int(self.MIN_SWIPE_LEN * self.FS)

        for s in self.y[self.start + self.END_WIN_LEN:]:
            win.append(abs(s))
            win.pop(0)
            i += 1

            # this checks if we've reached the end of the signal
            if i > min_index and sum(win) / len(win) < self.LOW_AVERAGE:
                return i - self.END_WIN_LEN
    end_time = cached_property(lambda self: self.end/self.FS)

    @memoize
    def smoothed(self, factor=None):
        if type(factor) == int:
            smoothed_sig = smooth(self.y, window_len=factor)

            # smoothing may return something longer than the original signal.
            # if it did then cut the ends off the smoothed signal
            if len(self.y) != len(smoothed_sig):
                diff = len(self.y) - len(smoothed_sig)
                start = abs(diff) / 2
                end = abs(diff) - start
                return smoothed_sig[start:end]
            else:
                return smoothed_sig
        else:
            # 'smoothing' parameter was None, so just return the signal
            return self.y

    @memoize
    def medfilt(self, window_size=7, smoothing=None):
        return scipy.signal.medfilt(self.smoothed(smoothing), window_size)

    @memoize
    def peaks(self, window_size=7, smoothing=10):
        return self.smoothed(smoothing) - self.medfilt(window_size, smoothing)

    @memoize
    def hist_threshold_filtered(self, extra=0.5, hist_win_size=200):
        """
        we need to get a cutoff amplitude for the (medfilt-signal) curve.  the
        prob is this cutoff changes.

        this will create a histogram, which allows me to find the cutoff
        threshold based on the local minimum of the histogram curve

        hist_win_size: is the range of the histogram bucket

        extra: this is diffucult to explain.  background: this function uses
        the histogram to determine the cutoff for peaks.  all values below the
        cutoff are zeroed out.  usually it is best if the cutoff is bumped up
        by about 1/2 a histogram window size.  this is the parameter to set
        that
        """
        tot_len = self.end - self.start
        htf = self.peaks().copy()
        for i in range(self.s.start, self.s.end, hist_win_size):
            hist, bin_edges = numpy.histogram(self.peaks()[i:i+hist_win_size])
            cutoff = abs(bin_edges[local_extrema(hist)[0][0] + 2])
            cutoff += extra * hist_win_size

            for j in range(i, i + hist_win_size):
                if abs(htf[t][j]) <= cutoff:
                    htf[t][j] = 0
        return htf