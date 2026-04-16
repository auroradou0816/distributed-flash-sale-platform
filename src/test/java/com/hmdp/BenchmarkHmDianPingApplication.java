package com.hmdp;

import com.hmdp.config.RedissonConfig;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@MapperScan("com.hmdp.mapper")
@SpringBootApplication
@ComponentScan(excludeFilters = {
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = HmDianPingApplication.class),
        @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = RedissonConfig.class)
})
public class BenchmarkHmDianPingApplication {

    public static void main(String[] args) {
        SpringApplication.run(BenchmarkHmDianPingApplication.class, args);
    }
}
