var pyrintApp = angular.module('pyrintApp', ['ui.bootstrap'])
/*
.config(function($routeProvider){
    $routeProvider
    .when('/', {
        templateUrl: 'home.html',
        controller: 'homeCtrl'
    })
    .when('/print', {
        templateUrl: 'print.html',
        controller: 'printCtrl'
    });
})*/
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
.factory('socketCon', ['$rootScope', function($rootScope){
    var socket = io.connect('http://' + document.domain + ':' + location.port);

    return {
        on: function(eventName, cb){
            socket.on(eventName, cb)
        },
        emit: function(eventName, data ,cb){
            socket.emit(eventName, data ,cb)
        }
    }
}])
.run(function($rootScope, socketCon){
    socketCon.on('online', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('online', data);
        });
    });

    socketCon.on('error', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('error', data);
        });
    });

    socketCon.on('disconnected', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('disconnected', data);
        });
    });

    socketCon.on('temperature', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('temperature', data);
        });
    });

    socketCon.on('started', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('started', data);
        });
    });

    socketCon.on('paused', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('paused', data);
        });
    });

    socketCon.on('resumed', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('resumed', data);
        });
    });


    socketCon.on('ended', function(data){
        $rootScope.$apply(function(){
            $rootScope.$broadcast('ended', data);
        });
    });
})
.controller('pyrintCtrl', function($scope, $http, $uibModal, socketCon){

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


    $scope.disconnect = function(){
        socketCon.emit('disconnect_printer');
    }

    $scope.startPrinting = function(){
        socketCon.emit('start_printing');
    }

    $scope.pausePrinting = function(){
        socketCon.emit('pause_printing');
    }

    $scope.cancelPrinting = function(){
        socketCon.emit('cancel_printing');
    }

    $scope.XYHome = function(){
        socketCon.emit('send_gcode', {'code': 'G28 X Y'});
        return false;
    }

    $scope.ZHome = function(){
        socketCon.emit('send_gcode', {'code': 'G28 Z'});
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

})
.controller('connectModalCtrl', function($scope, $http, $uibModalInstance, socketCon){

    $scope.portList = [];
    $scope.selectedPort = '';
    $scope.selectedBaud = 115200;
    $scope.connecting = false;
    $scope.cancelling = false;
    $scope.errMsg = null;

    $http.get('/ports.json').then(function(resp){
        $scope.portList = resp.data;
    });

    $scope.connect = function(){
        $scope.connecting = true;
        $scope.errMsg = null;
        socketCon.emit('connect_printer', {'port': $scope.selectedPort, 'baud': $scope.selectedBaud});
    }

    $scope.cancel = function(){
        socketCon.emit('disconnect_printer');
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