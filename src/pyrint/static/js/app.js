var pyrintApp = angular.module('pyrintApp', ['ui.bootstrap'])

.config(function($interpolateProvider){
    $interpolateProvider.startSymbol('[[').endSymbol(']]')
})
.directive("ngUploadChange",function(){
    return{
        scope:{
            ngUploadChange:"&"
        },
        link:function($scope, $element, $attrs){
            $element.on("change",function(event){
                $scope.$apply(function(){
                    $scope.ngUploadChange({$event: event})
                })
            })
            $scope.$on("$destroy",function(){
                $element.off();
            });
        }
    }
})
.run(function($rootScope){

    var ws = new WebSocket('ws://' + document.domain + ':' + location.port + '/ws');

    ws.onmessage = function (message) {
        o = JSON.parse(message.data);
        $rootScope.$apply(function(){
            $rootScope.$broadcast(o.event, o.args);
         });
    }
})
.controller('pyrintCtrl', function($scope, $http, $uibModal){

    $scope.reset = function(){
        $scope.online = false;
        $scope.printing = false;
        $scope.paused = false;

        $scope.port = null;
        $scope.baud = null;
        $scope.temp = null;

        $scope.gCodeFile = null;
        $scope.gCodeFileSize = null;
        $scope.gCodeLines = 0;
        $scope.gCodeLinesSent = 0;

        $scope.X = 0;
        $scope.Y = 0;
        $scope.Z = 0;

        $scope.progress = 0.0;

        $scope.uploading = false;
    }

    $scope.reset();

    $http.get('/state.json').then(function(resp){
        $scope.online = resp.data.online;
        $scope.printing = resp.data.printing;
        $scope.paused = resp.data.paused;

        $scope.port = resp.data.port;
        $scope.baud = resp.data.baud;
        $scope.temp = resp.data.temperature;

        if(resp.data.gcode!==null){
            $scope.gCodeFile = resp.data.gcode.file_name;
            $scope.gCodeFileSize = resp.data.gcode.file_size;
            $scope.gCodeLines = resp.data.gcode.lines;
            $scope.gCodeLinesSent = resp.data.gcode.lines_sent;
        }

        if(resp.data.pos!==null){
            $scope.X = resp.data.pos.x;
            $scope.Y = resp.data.pos.y;
            $scope.Z = resp.data.pos.z;
        }
    });

    $scope.openConnectModal = function(){
        $('.btn-connect').blur();
        $uibModal.open({
            templateUrl: 'connectModal.html',
            controller: 'connectModalCtrl',
            windowClass: 'connect-modal'
        });
    }

    $scope.$on('online', function(event, data){
         $scope.online = true;
         $scope.port = data.port;
         $scope.baud = data.baud;
    });

    $scope.$on('disconnected', function(event, data){
        $scope.reset();
    });

    $scope.$on('temperature', function(event, data){
         $scope.temp = data.temp;
    });

    $scope.$on('started', function(event, data){
        $scope.printing = true;
    });

    $scope.$on('ended', function(event, data){
        $scope.printing = false;
    });

    $scope.$on('paused', function(event, data){
        $scope.printing = false;
        $scope.paused = true;
    });

    $scope.$on('received', function(event, data){
        $scope.X = data.x;
        $scope.Y = data.y;
        $scope.Z = data.z;

        $scope.gCodeLinesSent = data.lines_sent;
        $scope.progress = parseFloat(($scope.gCodeLinesSent / $scope.gCodeLines) * 100).toFixed(2);

        console.log($scope.gCodeLines)
        console.log($scope.gCodeLinesSent)
        console.log('------------------------------')
    });

    $scope.disconnect = function(){
        $http.post('/disconnect');
    }

    $scope.startPrinting = function(){
        $http.post('/start');
    }

    $scope.pausePrinting = function(){
        $http.post('/pause');
    }

    $scope.cancelPrinting = function(){
        $http.post('/cancel');
    }

    $scope.XYHome = function(){
        $http.post('/run_gcode', {'code': 'G28 X Y'});
        return false;
    }

    $scope.ZHome = function(){
        $http.post('/run_gcode', {'code': 'G28 Z'});
        return false;
    }

    $scope.openFileDialog = function(){
        $('#thefile').trigger('click');
    }

    $scope.fileChanged = function($event){
        var files = $event.target.files;

        if(files.length<1){
            return;
        }

        var fileUploaded = files[0];
        var fileName = fileUploaded.name;

        var fileReader = new FileReader();
        fileReader.onload = function(fileLoadedEvent){
            var fileContents = fileLoadedEvent.target.result;

            $scope.uploading = true;
            $http.post('/upload_file', {'file_name': fileName, 'file_contents': fileContents}).then(function(resp){
                $scope.gCodeFile = resp.data.file_name;
                $scope.gCodeFileSize = resp.data.file_size;
                $scope.gCodeLines = resp.data.lines;
            }).finally(function(){
                 $scope.uploading = false;
            })
        };

        fileReader.readAsText(fileUploaded, 'UTF-8');
    }

    $scope.progressVal = function(){
        if($scope.gCodeLines){
             p = ($scope.gCodeLinesSent / $scope.gCodeLines) * 100;
             return parseFloat(p).toFixed(2);
          }
    }

})
.controller('connectModalCtrl', function($scope, $http, $uibModalInstance){

    $scope.portList = [];
    $scope.selectedPort = '';
    $scope.selectedBaud = 115200;
    $scope.connecting = false;
    $scope.cancelling = false;
    $scope.errMsg = null;

    $scope.loadData = function(){
        $http.get('/ports.json').then(function(resp){
            $scope.portList = resp.data;
        });
    }

    $scope.loadData();

    $scope.connect = function(){
        $scope.connecting = true;
        $scope.errMsg = null;
        $http.post('/connect', {'port': $scope.selectedPort, 'baud': $scope.selectedBaud});
        //socketCon.emit('connect_printer', {'port': $scope.selectedPort, 'baud': $scope.selectedBaud});
    }

    $scope.cancel = function(){
        // socketCon.emit('disconnect_printer');
        $scope.cancelling = true;
    }

    $scope.$on('disconnected', function(event, data){
        $scope.connecting = false;
        $scope.cancelling = false;
    });

    $scope.$on('error', function(event, data){
        $scope.connecting = false;
        $scope.cancelling = false;
        $scope.errMsg = data.msg;
    });

    $scope.$on('online', function(event, data){
        $scope.connecting = false;
        $scope.close();
    });

    $scope.close = function(){
        $uibModalInstance.dismiss('cancel');
    }
})